"""Pure-logic tests (no pyobjc): line grouping, locate, screen_contains, metric reader."""
from server.screen.match import group_lines, locate_match, screen_contains
from server.screen.metrics import TerminalMetricReader, parse_number
from server.screen.types import Block, Rect, ScreenObservation, Window

TERM = Window("Terminal", "train", Rect(900, 300, 700, 600))
CODE = Window("Code", "pinn_convection.py", Rect(0, 30, 860, 1000))
LOSS = r"epoch\s+(?P<step>\d+).*?loss\s+(?P<value>[0-9.eEOo+-]+)"


def blk(text, x, y, w=100, h=12, app="Terminal"):
    win = TERM if app == "Terminal" else CODE
    return Block(text, Rect(x, y, w, h), 0.9, app, win.title)


def obs_of(blocks):
    return ScreenObservation(t=0, app="Terminal", windows=[TERM, CODE], blocks=blocks, screen=Rect(0, 0, 1728, 1117))


def term_lines(rows):
    """rows: [(step, value)] -> blocks split the way Vision splits terminal rows."""
    out = []
    for i, (step, value) in enumerate(rows):
        y = 320 + 15 * i
        out += [blk("epoch", 990, y + 1, 40), blk(str(step), 1040, y - 1, 30), blk(f"loss {value}", 1085, y, 110)]
    return out


def test_group_lines_merges_split_row_regardless_of_order():
    lines = group_lines(term_lines([(2500, "2.5020e-01")]))
    assert [ln.text for ln in lines] == ["epoch 2500 loss 2.5020e-01"]


def test_group_lines_keeps_far_apart_panes_separate():
    lines = group_lines([blk("left pane", 0, 100, 80, app="Code"), blk("right pane", 600, 100, 80, app="Code")])
    assert len(lines) == 2


def test_locate_substring_regex_and_union():
    o = obs_of(term_lines([(100, "0.25"), (200, "0.24"), (300, "0.23")]) + [
        blk("19", 290, 470, 15, app="Code"), blk("def pde_residual(model, x, t, beta=BETA):", 330, 470, 300, app="Code"),
        blk("x.requires_grad_(True)", 350, 485, 160, app="Code")])
    r = locate_match(o, "def pde_residual", app="vscode")
    assert r and r.app == "Code" and r.rect.x < 330 and r.rect.x > 310  # gutter number excluded, padded
    r = locate_match(o, r"epoch\s+\d+", app="Terminal")
    assert r and r.matched.count("\n") == 2  # three consecutive rows unioned
    r = locate_match(o, "def pde_residual(model, x, t, beta=BETA):\n    x.requires_grad_(True)")
    assert r and r.rect.h > 25
    assert locate_match(o, "nonexistent_function") is None
    assert locate_match(o, "def pde_residual", app="Terminal") is None


def test_locate_fuzzy_survives_ocr_noise():
    o = obs_of([blk("u_x = torch.autograd-grad(u.sum(), x, create_graph=True) [0]", 350, 500, 400, app="Code")])
    r = locate_match(o, "u_x = torch.autograd.grad(u.sum(), x, create_graph=True)[0]")
    assert r is not None and r.score >= 90


def test_locate_exact_hit_beats_neighbouring_near_miss():
    o = obs_of(term_lines([(2000, "2.5068e-01"), (2100, "2.5070e-01")]))
    r = locate_match(o, "loss 2.5068e-01")
    assert r and "2100" not in r.matched


def test_screen_contains():
    o = obs_of([blk("return u_t + beta * u_x", 350, 500, 200, app="Code")])
    assert screen_contains(o, r"u_t\s*\+\s*beta\s*\*\s*u_x", app="Code")
    assert not screen_contains(o, r"u_t\s*\+\s*beta", app="Terminal")
    assert screen_contains(o, "return u_t+beta*u_x")  # whitespace-insensitive literal


def test_parse_number_fixes_ocr_digits():
    assert parse_number("2.5O16e-01") == 0.25016
    assert parse_number("l.5") == 1.5


def test_metric_reader_dedups_and_reads_new_lines():
    got = []
    r = TerminalMetricReader("pinn", {"loss": LOSS}, lambda n, s, v: got.append((s, v)), app="Terminal")
    r.feed(obs_of(term_lines([(0, "0.25"), (100, "0.24")])))
    r.feed(obs_of(term_lines([(0, "0.25"), (100, "0.24"), (200, "0.23")])))
    r.feed(obs_of(term_lines([(100, "0.24"), (200, "0.23"), (300, "0.22")])))  # scrolled
    assert got == [(0, 0.25), (100, 0.24), (200, 0.23), (300, 0.22)]
    assert r.run_id == "screen-pinn"


def test_metric_reader_detects_restart():
    got, restarts = [], []
    r = TerminalMetricReader("pinn", {"loss": LOSS}, lambda n, s, v: got.append((s, v)),
                             on_restart=restarts.append)
    r.feed(obs_of(term_lines([(0, "0.2504"), (100, "0.2503"), (200, "0.2505")])))
    # learner re-runs with the β curriculum: old lines still visible above the new ones
    old = [(0, "0.2504"), (100, "0.2503"), (200, "0.2505")]
    r.feed(obs_of(term_lines(old + [(0, "0.2400")])))
    r.feed(obs_of(term_lines(old + [(0, "0.2400"), (100, "0.1100")])))
    assert restarts == ["screen-pinn-r2"] and r.run_id == "screen-pinn-r2"
    assert got[-2:] == [(0, 0.24), (100, 0.11)]


def test_metric_reader_ignores_other_apps():
    got = []
    r = TerminalMetricReader("pinn", {"loss": LOSS}, lambda n, s, v: got.append(s), app="Terminal")
    r.feed(obs_of([blk("epoch 5 loss 0.1", 350, 500, 200, app="Code")]))
    assert got == []


def test_tiger_writer_disabled_without_real_url():
    from server.screen.metrics import TigerWriter
    assert not TigerWriter("").enabled
    assert not TigerWriter("postgres://...").enabled
    assert TigerWriter("postgres://u:p@abc.tsdb.cloud.timescale.com:5432/tsdb").enabled
    TigerWriter("").write("r", [("loss", 1, 0.5)])  # must not raise
