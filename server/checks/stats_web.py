"""Read-only Tiger Data stats page, served by the engine (Tiger Data track: judges SEE Tiger).

Mount in the orchestrator (E4):

    from server.checks.stats_web import router as stats_router
    app.include_router(stats_router)

Then open http://localhost:8787/stats (``STATS_URL``). The page polls ``/stats/data`` every 2 s:

* the live metric curve of the current run from the ``metrics_1s`` continuous aggregate,
  with the tutorial's reference curve (same lesson) overlaid, aligned by step;
* time per step (``time_per_step``) and check fail rate (``check_fail_rate``) for the lesson;
* the stuck heatmap per 15 s of video (``stuck_heatmap``);
* ingest rows/s and the measured query latency of each panel.

When Tiger is unreachable the payload is ``{"online": false, "spool": {...}}`` and the page says
"Tiger offline: N rows spooled, will upload on reconnect". It never shows stale or made-up numbers.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from .curves import find_reference_run
from .tiger import _redact, spool_status, stats

STATS_URL = "http://localhost:8787/stats"
OPEN_STATS_LINK = f'<a href="{STATS_URL}" target="_blank" rel="noopener">Open stats</a>'

router = APIRouter()

OFFLINE_BACKOFF_S = 10.0  # after a failed connect, answer "offline" instantly for this long
CONNECT_TIMEOUT_S = 3

# ---------------------------------------------------------------- queries (all read the caggs)
SQL_CURRENT_RUN = """
SELECT run_id FROM training_metrics
WHERE time > now() - interval '1 day'
  AND run_id NOT IN (SELECT id FROM runs WHERE source = 'tutorial')
ORDER BY time DESC LIMIT 1
"""
SQL_CURRENT_LESSON = "SELECT lesson_id FROM learning_events WHERE lesson_id IS NOT NULL ORDER BY time DESC LIMIT 1"
SQL_LESSON_OF_RUN = "SELECT lesson_id FROM runs WHERE id = %s"
# 'learner' | 'demo' (a Demo lesson's recorded run: labelled as a recording, never as the learner's live run) | None
SQL_SOURCE_OF_RUN = "SELECT source FROM runs WHERE id = %s"
SQL_CURVE = """
SELECT name, step, value FROM metrics_1s
WHERE run_id = %s AND bucket > now() - interval '6 hours'
ORDER BY bucket
"""
SQL_REF_CURVE = "SELECT name, step, value FROM metrics_1s WHERE run_id = %s ORDER BY step"
SQL_TIME_PER_STEP = """
SELECT step_id, sum(passes) AS passes,
       sum(avg_s * passes) / NULLIF(sum(passes), 0) AS avg_s, min(min_s) AS min_s, max(max_s) AS max_s
FROM time_per_step WHERE lesson_id = %s GROUP BY step_id ORDER BY step_id
"""
SQL_FAIL_RATE = """
SELECT step_id, check_id, sum(fails) AS fails, sum(passes) AS passes, sum(evaluations) AS evaluations,
       sum(fails)::double precision / NULLIF(sum(evaluations), 0) AS fail_rate
FROM check_fail_rate WHERE lesson_id = %s GROUP BY step_id, check_id
ORDER BY fail_rate DESC NULLS LAST, evaluations DESC LIMIT 20
"""
SQL_SOURCE_OF_LESSON = """
SELECT source_id FROM learning_events WHERE lesson_id = %s AND source_id IS NOT NULL ORDER BY time DESC LIMIT 1
"""
SQL_STUCK = """
SELECT video_bucket, sum(stuck) AS stuck FROM stuck_heatmap
WHERE (%(source)s::text IS NULL OR source_id = %(source)s) AND bucket > now() - interval '30 days'
GROUP BY video_bucket ORDER BY video_bucket
"""


class _Db:
    """One shared autocommit connection, reconnected on failure, with an offline back-off."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.conn: Any = None
        self.down_until = 0.0
        self.last_error: str | None = None
        self.connect = self._default_connect  # swapped in tests

    @staticmethod
    def _default_connect() -> Any:
        import os

        import psycopg

        from .tiger import load_env

        load_env()
        dsn = os.environ.get("TIGER_DATABASE_URL", "")
        if not dsn or "..." in dsn:
            raise LookupError("TIGER_DATABASE_URL not set")
        try:
            return psycopg.connect(dsn, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S)
        except Exception as exc:
            raise ConnectionError(_redact(str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__, dsn)) from None

    def get(self) -> Any:
        if self.conn is not None:
            return self.conn
        if time.monotonic() < self.down_until:
            raise ConnectionError(self.last_error or "offline")
        try:
            self.conn = self.connect()
            self.last_error = None
            return self.conn
        except Exception as exc:
            self.mark_down(str(exc) or type(exc).__name__)
            raise ConnectionError(self.last_error) from None

    def mark_down(self, why: str) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:  # noqa: BLE001, S110
                pass
        self.conn = None
        self.last_error = why[:200]
        self.down_until = time.monotonic() + OFFLINE_BACKOFF_S


DB = _Db()


def _timed(conn: Any, sql: str, params: Any, timings: dict, key: str) -> list:
    t0 = time.perf_counter()
    rows = conn.execute(sql, params).fetchall()
    timings[key] = round((time.perf_counter() - t0) * 1000, 2)
    return rows


def _num(v: Any) -> float | None:
    if v is None:
        return None
    f = float(v)
    return f if f == f and abs(f) != float("inf") else None  # NaN/inf aren't JSON


def _curves(rows: list) -> dict[str, list[list[float | None]]]:
    out: dict[str, list] = {}
    for name, step, value in rows:
        out.setdefault(name, []).append([step, _num(value)])
    return out


def collect(run_id: str | None = None, lesson_id: str | None = None, source_id: str | None = None) -> dict:
    """Everything the page shows, straight from Tiger. ``online: false`` when Tiger is unreachable."""
    offline = lambda why: {"online": False, "error": why, "spool": spool_status()}  # noqa: E731
    with DB.lock:
        try:
            conn = DB.get()
        except ConnectionError as exc:
            return offline(str(exc))
        try:
            timings: dict[str, float] = {}
            if not run_id:
                r = conn.execute(SQL_CURRENT_RUN).fetchone()
                run_id = r[0] if r else None
            if not lesson_id and run_id:
                r = conn.execute(SQL_LESSON_OF_RUN, (run_id,)).fetchone()
                lesson_id = r[0] if r else (run_id[len("screen-"):] if run_id.startswith("screen-") else None)
            if not lesson_id:
                r = conn.execute(SQL_CURRENT_LESSON).fetchone()
                lesson_id = r[0] if r else None
            data: dict[str, Any] = {"online": True, "run_id": run_id, "lesson_id": lesson_id, "run_source": None,
                                    "curve": {}, "reference": None, "time_per_step": [], "check_fail_rate": [],
                                    "stuck": [], "timings_ms": timings}
            if run_id:
                r = conn.execute(SQL_SOURCE_OF_RUN, (run_id,)).fetchone()
                data["run_source"] = r[0] if r else None
                data["curve"] = _curves(_timed(conn, SQL_CURVE, (run_id,), timings, "curve (metrics_1s)"))
                ref = find_reference_run(conn, run_id, lesson_id)
                if ref:
                    data["reference"] = {"run_id": ref, "curve": _curves(_timed(conn, SQL_REF_CURVE, (ref,), timings,
                                                                                 "reference (metrics_1s)"))}
            if lesson_id:
                data["time_per_step"] = [
                    {"step_id": s, "passes": int(p or 0), "avg_s": _num(a), "min_s": _num(mn), "max_s": _num(mx)}
                    for s, p, a, mn, mx in _timed(conn, SQL_TIME_PER_STEP, (lesson_id,), timings, "time_per_step")]
                data["check_fail_rate"] = [
                    {"step_id": s, "check_id": c, "fails": int(f or 0), "passes": int(p or 0),
                     "evaluations": int(e or 0), "fail_rate": _num(rate)}
                    for s, c, f, p, e, rate in _timed(conn, SQL_FAIL_RATE, (lesson_id,), timings, "check_fail_rate")]
                if not source_id:
                    r = conn.execute(SQL_SOURCE_OF_LESSON, (lesson_id,)).fetchone()
                    source_id = r[0] if r else None
            data["source_id"] = source_id
            data["stuck"] = [{"video_t": _num(v), "stuck": int(n or 0)}
                             for v, n in _timed(conn, SQL_STUCK, {"source": source_id}, timings, "stuck_heatmap")]
            st = stats(conn, runs=1)
            data["ingest"] = {"rows_per_s": round(st["training_metrics"]["rows_per_s"] + st["learning_events"]["rows_per_s"], 1),
                              "metrics_total": st["training_metrics"]["total"],
                              "events_total": st["learning_events"]["total"], "chunks": st["chunks"]}
            data["spool"] = spool_status()
            return data
        except Exception as exc:  # noqa: BLE001  (dropped connection, missing view...)
            DB.mark_down(str(exc).strip().splitlines()[0][:160] if str(exc).strip() else type(exc).__name__)
            return offline(DB.last_error or "query failed")


@router.get("/stats/data")
def stats_data(run_id: str | None = Query(None), lesson_id: str | None = Query(None),
               source_id: str | None = Query(None)) -> dict:
    return collect(run_id, lesson_id, source_id)


@router.get("/stats", response_class=HTMLResponse)
def stats_page() -> str:
    return PAGE


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tiger Stats</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#f6f6f4;--card:#fff;--ink:#1c1c1e;--mute:#6e6e73;--line:#e3e3e0;--accent:#e8752d;--ref:#8e8e93;--bad:#d1453b;--ok:#2f9e61}
@media (prefers-color-scheme:dark){:root{--bg:#141415;--card:#1d1d1f;--ink:#f2f2f2;--mute:#9a9aa0;--line:#2e2e31;--ref:#77777d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif}
header{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:baseline;padding:18px 20px 6px}
h1{font-size:18px;margin:0;font-weight:650}#meta{color:var(--mute)}
#banner{display:none;margin:10px 20px;padding:12px 14px;border-radius:10px;background:#fff3e0;color:#7a3e00;border:1px solid #f3c58f;font-weight:600}
@media (prefers-color-scheme:dark){#banner{background:#3a2610;color:#ffcf99;border-color:#6b4519}}
.kpis{display:flex;flex-wrap:wrap;gap:10px;padding:8px 20px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:150px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.kpi span{color:var(--mute);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px;padding:10px 20px 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}
.card h2{font-size:13px;margin:0 0 2px;font-weight:650}.card .src{color:var(--mute);font-size:12px;margin-bottom:8px}
.empty{color:var(--mute);padding:30px 0;text-align:center}
canvas{max-height:260px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
td,th{padding:5px 6px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}th{color:var(--mute);font-weight:500}
.bar{height:6px;border-radius:3px;background:var(--bad)}
@media (max-width:420px){.grid{grid-template-columns:1fr;padding:8px 16px}.kpis,header{padding-left:16px;padding-right:16px}}
</style></head><body>
<header><h1>Tiger Data, live</h1><div id="meta">connecting…</div></header>
<div id="banner"></div>
<div class="kpis">
 <div class="kpi"><b id="k-rate">–</b><span>rows/s ingested (last 10 s)</span></div>
 <div class="kpi"><b id="k-rows">–</b><span>metric rows · event rows</span></div>
 <div class="kpi"><b id="k-q">–</b><span>slowest panel query (ms)</span></div>
 <div class="kpi"><b id="k-chunks">–</b><span>hypertable chunks</span></div>
</div>
<div class="grid">
 <div class="card" style="grid-column:1/-1"><h2>Live metric curve</h2><div class="src" id="s-curve">metrics_1s continuous aggregate</div><canvas id="c-curve"></canvas><div class="empty" id="e-curve">no metrics yet</div></div>
 <div class="card"><h2>Time per step</h2><div class="src">time_per_step continuous aggregate</div><canvas id="c-steps"></canvas><div class="empty" id="e-steps">no step passed yet</div></div>
 <div class="card"><h2>Where learners get stuck</h2><div class="src">stuck_heatmap continuous aggregate · per 15 s of video</div><canvas id="c-stuck"></canvas><div class="empty" id="e-stuck">no off-track moments yet</div></div>
 <div class="card"><h2>Check fail rate</h2><div class="src">check_fail_rate continuous aggregate</div><table><thead><tr><th>step</th><th>check</th><th>fails / runs</th><th style="width:30%">rate</th></tr></thead><tbody id="t-fail"></tbody></table><div class="empty" id="e-fail">no checks evaluated yet</div></div>
 <div class="card"><h2>Query latency</h2><div class="src">measured on each refresh</div><table><tbody id="t-ms"></tbody></table></div>
</div>
<script>
const $=id=>document.getElementById(id), css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const params=new URLSearchParams(location.search), charts={};
function mmss(t){t=Math.round(t||0);return Math.floor(t/60)+":"+String(t%60).padStart(2,"0")}
const EMPTY={};
function show(id,has,why){const e=$("e-"+id);EMPTY[id]??=e.textContent;e.textContent=why||EMPTY[id];
 $("c-"+id)&&($("c-"+id).style.display=has?"":"none");e.style.display=has?"none":""}
function chart(id,cfg){if(!window.Chart)return;if(charts[id]){charts[id].data=cfg.data;charts[id].options=cfg.options;charts[id].update("none");return}
 charts[id]=new Chart($("c-"+id),cfg)}
function rows(tbody,list){const tb=$(tbody);tb.replaceChildren();for(const cells of list){const tr=document.createElement("tr");
 for(const c of cells){const td=document.createElement("td");if(c instanceof Node)td.append(c);else td.textContent=c;tr.append(td)}tb.append(tr)}}
function offline(d){
 $("banner").style.display="block";
 $("banner").textContent="Tiger offline: "+d.spool.rows+" rows spooled, will upload on reconnect"+(d.error?" ("+d.error+")":"");
 $("meta").textContent="spool: "+d.spool.dir;
 for(const k of ["k-rate","k-rows","k-q","k-chunks"])$(k).textContent="–";
 for(const id of ["curve","steps","stuck","fail"])show(id,false,"Tiger offline: nothing shown until it reconnects");
 $("t-fail").replaceChildren();$("t-ms").replaceChildren();
}
function render(d){
 if(!d.online)return offline(d);
 $("banner").style.display=d.spool&&d.spool.rows?"block":"none";
 if(d.spool&&d.spool.rows)$("banner").textContent="Tiger online · uploading "+d.spool.rows+" spooled rows";
 const demo=d.run_source==="demo";
 $("meta").textContent="lesson "+(d.lesson_id||"–")+" · run "+(d.run_id||"–")+(demo?" (Demo recording, not a live run)":"")+" · refreshed "+new Date().toLocaleTimeString();
 $("k-rate").textContent=d.ingest.rows_per_s;$("k-rows").textContent=d.ingest.metrics_total.toLocaleString()+" · "+d.ingest.events_total.toLocaleString();
 const ms=Object.values(d.timings_ms);$("k-q").textContent=ms.length?Math.max(...ms).toFixed(1):"–";$("k-chunks").textContent=d.ingest.chunks??"–";
 // live curve (+ tutorial reference)
 const names=Object.keys(d.curve), metric=params.get("metric")||(names.includes("loss")?"loss":names[0]);
 show("curve",!!metric);
 if(metric){const pts=d.curve[metric].filter(p=>p[1]!==null).map(p=>({x:p[0],y:p[1]}));
  const ds=[{label:metric+(demo?" (Demo recording)":" (you)"),data:pts,borderColor:css("--accent"),backgroundColor:css("--accent"),pointRadius:0,borderWidth:2,tension:.2}];
  const ref=d.reference&&d.reference.curve[metric];
  if(ref)ds.push({label:"tutorial",data:ref.filter(p=>p[1]!==null).map(p=>({x:p[0],y:p[1]})),borderColor:css("--ref"),borderDash:[5,4],pointRadius:0,borderWidth:1.5});
  const pos=pts.every(p=>p.y>0)&&(!ref||ref.every(p=>p[1]===null||p[1]>0));
  $("s-curve").textContent=(demo?"Demo recording (replayed output, not a live run) · ":"")+"metrics_1s continuous aggregate · "+pts.length+" buckets"+(ref?" · dashed = tutorial reference ("+d.reference.run_id+")":"");
  chart("curve",{type:"line",data:{datasets:ds},options:{animation:false,parsing:false,responsive:true,
   scales:{x:{type:"linear",title:{display:true,text:"training step"}},y:{type:pos?"logarithmic":"linear",title:{display:true,text:metric}}},
   plugins:{legend:{labels:{boxWidth:12}}}}})}
 // time per step
 show("steps",d.time_per_step.length>0);
 chart("steps",{type:"bar",data:{labels:d.time_per_step.map(s=>s.step_id),datasets:[{label:"avg seconds",data:d.time_per_step.map(s=>s.avg_s),backgroundColor:css("--accent")}]},
  options:{animation:false,plugins:{legend:{display:false}},scales:{y:{title:{display:true,text:"seconds"}}}}});
 // stuck heatmap
 show("stuck",d.stuck.length>0);const mx=Math.max(1,...d.stuck.map(s=>s.stuck));
 chart("stuck",{type:"bar",data:{labels:d.stuck.map(s=>mmss(s.video_t)),datasets:[{label:"stuck",data:d.stuck.map(s=>s.stuck),
  backgroundColor:d.stuck.map(s=>"rgba(209,69,59,"+(0.25+0.75*s.stuck/mx)+")")}]},
  options:{animation:false,plugins:{legend:{display:false}},scales:{x:{title:{display:true,text:"video time"}},y:{title:{display:true,text:"off-track + failed checks"}}}}});
 // fail rate
 show("fail",d.check_fail_rate.length>0);
 rows("t-fail",d.check_fail_rate.map(c=>{const b=document.createElement("div");b.className="bar";b.style.width=Math.round(100*(c.fail_rate||0))+"%";
  const w=document.createElement("div");w.append(b);w.title=Math.round(100*(c.fail_rate||0))+"%";return [c.step_id||"–",c.check_id||"–",c.fails+" / "+c.evaluations,w]}));
 rows("t-ms",Object.entries(d.timings_ms).map(([k,v])=>[k,v.toFixed(2)+" ms"]));
}
async function tick(){
 try{const q=new URLSearchParams();for(const k of ["run_id","lesson_id","source_id"])if(params.get(k))q.set(k,params.get(k));
  const r=await fetch("/stats/data?"+q);render(await r.json())}
 catch(e){$("meta").textContent="engine not reachable ("+e.message+")"}
 setTimeout(tick,2000)}
tick();
</script></body></html>
"""
