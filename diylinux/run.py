"""Command runner with dry-run and a log callback. Every shell interaction goes through here."""
from __future__ import annotations

import os
import shlex
import subprocess
from typing import Callable

DRY = os.environ.get("DIYLINUX_DRYRUN") == "1"
LogFn = Callable[[str], None]
_log: LogFn = print


def set_logger(fn: LogFn) -> None:
    global _log
    _log = fn


def log(msg: str) -> None:
    _log(msg)


class CommandError(RuntimeError):
    pass


def run(cmd: list[str], *, check: bool = True, input: str | None = None, env: dict | None = None,
        capture: bool = False, quiet: bool = False) -> str:
    """Run a command, streaming output to the log. Returns captured stdout if capture=True."""
    shown = " ".join(shlex.quote(c) for c in cmd)
    if not quiet:
        log(f"$ {shown}")
    if DRY:
        return ""
    full_env = dict(os.environ)
    full_env.update({"DEBIAN_FRONTEND": "noninteractive", "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"})
    if env:
        full_env.update(env)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=full_env,
                            errors="replace")
    out_lines: list[str] = []
    if input is not None:
        proc.stdin.write(input)  # type: ignore[union-attr]
        proc.stdin.close()      # type: ignore[union-attr]
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        out_lines.append(line)
        if not capture and not quiet:
            log("  " + line)
    rc = proc.wait()
    if check and rc != 0:
        tail = "\n".join(out_lines[-15:])
        raise CommandError(f"command failed ({rc}): {shown}\n{tail}")
    return "\n".join(out_lines)


def write_file(path: str, content: str, mode: int | None = None) -> None:
    log(f"write {path}")
    if DRY:
        for l in content.rstrip("\n").splitlines():
            log("  | " + l)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    if mode is not None:
        os.chmod(path, mode)


def append_file(path: str, content: str) -> None:
    log(f"append {path}")
    if DRY:
        return
    with open(path, "a") as f:
        f.write(content)
