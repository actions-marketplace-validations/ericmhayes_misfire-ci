"""Cost-discipline helpers.

Never feed whole logs to the model: take the failing tail plus the stack
frames that matter.
"""

from __future__ import annotations

import re

# Rough token budget for the log slice handed to the agent. Tune with count_tokens.
_DEFAULT_TAIL_LINES = 200
# How many lines to keep from the first error block found in the dropped head.
_HEAD_BLOCK_LINES = 20
# Lines that signal the originating failure (pytest 'E ', tracebacks, CI markers).
_ERROR_RE = re.compile(
    r"traceback|exception|error[:\s]|assert|\bFAIL(ED|URE)?\b|^E\s", re.IGNORECASE
)


def truncate_logs(logs: str, tail_lines: int = _DEFAULT_TAIL_LINES) -> str:
    """Reduce a raw CI log to the portion that carries the failure signal.

    The failure and its stack usually sit at the *end* of a CI log, so we keep
    the last `tail_lines` lines. When the log is longer than that, we also scan
    the dropped head for the first error/traceback line and prepend a short block
    starting there — otherwise a very long log would bury the originating error
    above the tail window. Short logs are returned unchanged.

    This could later widen (multiple stack frames, per-step slicing).
    """
    lines = logs.splitlines()
    if len(lines) <= tail_lines:
        return logs

    tail = lines[-tail_lines:]
    head = lines[:-tail_lines]  # the part we would otherwise drop

    first_err = next((i for i, ln in enumerate(head) if _ERROR_RE.search(ln)), None)
    if first_err is None:
        return "\n".join([f"... [{len(head)} earlier lines truncated] ...", *tail])

    head_block = head[first_err : first_err + _HEAD_BLOCK_LINES]
    dropped_before = first_err
    dropped_between = len(head) - first_err - len(head_block)
    out = []
    if dropped_before:
        out.append(f"... [{dropped_before} earlier lines truncated] ...")
    out.extend(head_block)
    if dropped_between:
        out.append(f"... [{dropped_between} lines truncated] ...")
    out.extend(tail)
    return "\n".join(out)
