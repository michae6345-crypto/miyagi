"""Run a command under a PTY, pass its output through byte-for-byte, and tee lines to the sinks.

Why a PTY: the child sees a terminal, so it keeps colors and line-buffers its
output (Python, tqdm, PyTorch logs stay live). stdout and stderr share the PTY,
the way they share a terminal. ONLCR is turned off on the PTY so the bytes we
forward are exactly the bytes the program wrote.

Windows has no PTY module (no pty, termios, fcntl, select on pipes): there the
child's stdout and stderr share one pipe instead (_run_pipe), with
PYTHONUNBUFFERED=1 so a Python program's lines still arrive as it prints them.
"""
from __future__ import annotations

import collections
import errno
import os
import signal
import struct
import subprocess
import sys
from collections.abc import Callable

if os.name != "nt":
    import fcntl
    import pty
    import select
    import termios

from .metrics import PREFIX, clean_line

LineHandler = Callable[[str], None]


def _copy_winsize(src_fd: int, dst_fd: int) -> None:
    try:
        ws = fcntl.ioctl(src_fd, termios.TIOCGWINSZ, b"\0" * 8)
        fcntl.ioctl(dst_fd, termios.TIOCSWINSZ, ws)
    except (OSError, ValueError):
        fcntl.ioctl(dst_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))


class _Display:
    """Writes child output to our stdout; optionally hides ::metric:: lines (line-granular)."""

    def __init__(self, hide_metrics: bool):
        self.hide = hide_metrics
        self.out = sys.stdout.buffer
        self.held = b""  # a partial line that might turn out to be a ::metric:: line
        self.prefix = PREFIX.encode()

    def _maybe_metric(self, partial: bytes) -> bool:
        s = partial.lstrip()
        return self.prefix.startswith(s) or s.startswith(self.prefix)

    def write(self, data: bytes) -> None:
        if not self.hide:
            self.out.write(data)
            self.out.flush()
            return
        data = self.held + data
        self.held = b""
        parts = data.split(b"\n")
        tail = parts.pop()
        out = bytearray()
        for p in parts:
            if not p.lstrip().startswith(self.prefix):
                out += p + b"\n"
        if tail and self._maybe_metric(tail):
            self.held = tail
        else:
            out += tail
        if out:
            self.out.write(bytes(out))
            self.out.flush()

    def finish(self) -> None:
        if self.held and not self.held.lstrip().startswith(self.prefix):
            self.out.write(self.held)
            self.out.flush()
        self.held = b""


def run_pty(argv: list[str], on_line: LineHandler, hide_metrics: bool = False, tail_lines: int = 200,
            env: dict | None = None) -> tuple[int, list[str]]:
    """Run argv, stream it, call on_line(clean_line) per line. Returns (exit_code, last lines)."""
    if os.name == "nt":
        return _run_pipe(argv, on_line, hide_metrics, tail_lines, env)
    master, slave = pty.openpty()
    attrs = termios.tcgetattr(slave)
    attrs[1] &= ~termios.ONLCR  # oflag: don't turn \n into \r\n
    termios.tcsetattr(slave, termios.TCSANOW, attrs)
    if sys.stdout.isatty():
        _copy_winsize(sys.stdout.fileno(), slave)
    else:
        _copy_winsize(-1, slave)

    try:
        proc = subprocess.Popen(
            argv,
            stdin=None,  # inherit: interactive input (pdb, input()) still works
            stdout=slave,
            stderr=slave,
            env=env,
            close_fds=True,
        )
    except FileNotFoundError:
        os.close(master)
        os.close(slave)
        msg = f"tut: command not found: {argv[0]}"
        print(msg, file=sys.stderr)
        on_line(msg)
        return 127, [msg]
    except PermissionError:
        os.close(master)
        os.close(slave)
        msg = f"tut: permission denied: {argv[0]}"
        print(msg, file=sys.stderr)
        on_line(msg)
        return 126, [msg]
    os.close(slave)

    # Ctrl-C reaches the child through the terminal's process group; we just keep reading
    # so we can record how it ended.
    old_int = signal.signal(signal.SIGINT, lambda *_: None)
    old_winch = None
    if sys.stdout.isatty():
        old_winch = signal.signal(signal.SIGWINCH, lambda *_: _copy_winsize(sys.stdout.fileno(), master))

    display = _Display(hide_metrics)
    tail: collections.deque[str] = collections.deque(maxlen=tail_lines)
    buf = b""
    try:
        while True:
            try:
                r, _, _ = select.select([master], [], [], 0.25)
            except InterruptedError:
                continue
            if not r:
                if proc.poll() is not None:
                    # child gone; drain anything left without blocking forever (grandchildren may hold the pty)
                    r2, _, _ = select.select([master], [], [], 0.05)
                    if not r2:
                        break
                continue
            try:
                data = os.read(master, 65536)
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.EBADF):  # EIO = slave closed (child exited)
                    break
                raise
            if not data:
                break
            display.write(data)
            buf += data
            *lines, buf = buf.split(b"\n")
            for raw in lines:
                line = clean_line(raw.decode("utf-8", "replace"))
                tail.append(line)
                on_line(line)
    finally:
        display.finish()
        if buf:
            line = clean_line(buf.decode("utf-8", "replace"))
            tail.append(line)
            on_line(line)
        os.close(master)
        code = proc.wait()
        signal.signal(signal.SIGINT, old_int)
        if old_winch is not None:
            signal.signal(signal.SIGWINCH, old_winch)
    if code < 0:  # killed by a signal → shell convention
        code = 128 + (-code)
    return code, list(tail)


def _run_pipe(argv: list[str], on_line: LineHandler, hide_metrics: bool, tail_lines: int,
              env: dict | None) -> tuple[int, list[str]]:
    """Windows: run_pty without a PTY. stdout and stderr share one pipe; stdin stays the console's (input() works).
    The child sees a pipe, so colors may be off and Python would block-buffer: PYTHONUNBUFFERED=1 keeps its lines live.
    A bare program name is looked up with PATHEXT first (npm -> npm.cmd), as the shell would."""
    import shutil

    child_env = dict(os.environ if env is None else env)
    child_env.setdefault("PYTHONUNBUFFERED", "1")
    argv = list(argv)
    if argv and not os.path.dirname(argv[0]):
        argv[0] = shutil.which(argv[0], path=child_env.get("PATH")) or argv[0]
    try:
        proc = subprocess.Popen(argv, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=child_env)
    except FileNotFoundError:
        msg = f"tut: command not found: {argv[0]}"
        print(msg, file=sys.stderr)
        on_line(msg)
        return 127, [msg]
    except PermissionError:
        msg = f"tut: permission denied: {argv[0]}"
        print(msg, file=sys.stderr)
        on_line(msg)
        return 126, [msg]
    # Ctrl+C reaches the child through the shared console; we keep reading so we can record how it ended.
    old_int = signal.signal(signal.SIGINT, lambda *_: None)
    display = _Display(hide_metrics)
    tail: collections.deque[str] = collections.deque(maxlen=tail_lines)
    buf = b""
    try:
        assert proc.stdout is not None
        while True:
            data = proc.stdout.read1(65536)
            if not data:
                break
            display.write(data)
            buf += data
            *lines, buf = buf.split(b"\n")
            for raw in lines:
                line = clean_line(raw.decode("utf-8", "replace"))  # clean_line drops the \r of \r\n
                tail.append(line)
                on_line(line)
    finally:
        display.finish()
        if buf:
            line = clean_line(buf.decode("utf-8", "replace"))
            tail.append(line)
            on_line(line)
        if proc.stdout is not None:
            proc.stdout.close()
        code = proc.wait()
        signal.signal(signal.SIGINT, old_int)
    return code, list(tail)
