"""Render a Verdict into a Markdown PR comment body."""

from __future__ import annotations

import re

from .schema import FlakyClassification, Verdict

# Caps on the free-text, model-authored fields (defense against a hostile log
# steering the model into a wall of text).
_ROOT_CAUSE_LIMIT = 2000
_SUGGESTED_FIX_LIMIT = 1000

_NEWLINES = re.compile(r"\s*[\r\n]+\s*")


def _safe_inline(text: str, *, limit: int) -> str:
    """Make model-authored text safe to interpolate into the Markdown comment.

    `root_cause`/`suggested_fix` are influenced by attacker-controlled log/diff
    content, so before rendering we:
      - cap the length,
      - collapse to a single line (no injecting new Markdown blocks, headings,
        or a second hidden `MARKER` to hijack the upsert),
      - HTML-escape `& < >` (neutralizes raw HTML like `<img onerror=...>` and
        autolinks), and
      - escape `[` `]` so Markdown links/images `[x](url)` / `![x](url)` render
        as inert text, and
      - defang bare URLs so GitHub can't autolink an attacker-controlled link.
    """
    text = text.strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    text = _NEWLINES.sub(" ", text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("[", "\\[").replace("]", "\\]")
    text = text.replace("https://", "hxxps://").replace("http://", "hxxp://")
    return text

# Hidden HTML marker embedded in every advisory so Misfire can find and update
# its own prior comment (upsert) instead of posting a new one each run.
MARKER = "<!-- misfire:advisory -->"

_FOOTER = (
    "\n\n---\n"
    "<sub>🔧 Posted by [Misfire](https://github.com/ericmhayes/misfire-ci) — "
    "advisory only, nothing was changed or blocked.</sub>"
)

# Human-facing label + icon per classification.
_FLAKY_LABELS = {
    FlakyClassification.REAL: "🔴 Likely a real failure",
    FlakyClassification.LIKELY_FLAKY: "🟡 Likely flaky",
    FlakyClassification.UNKNOWN: "⚪ Flakiness unknown",
}


def render_comment(verdict: Verdict) -> str:
    """Turn the agent's Verdict into the Markdown body posted to the PR.

    Root cause + category + optional fix + confidence, plus the deterministic
    real-vs-flaky verdict line when a test was implicated.
    """
    lines = [
        "### 🔧 Misfire — build failure analysis",
        "",
        f"**Root cause:** {_safe_inline(verdict.root_cause, limit=_ROOT_CAUSE_LIMIT)}",
        f"**Category:** `{verdict.category.value}`",
        f"**Confidence:** {verdict.confidence:.0%}",
    ]
    if verdict.flaky is not None:
        label = _FLAKY_LABELS[verdict.flaky.classification]
        # rationale is generated deterministically by flaky.classify, but sanitize
        # it anyway so the invariant is enforced rather than merely assumed.
        rationale = _safe_inline(verdict.flaky.rationale, limit=_SUGGESTED_FIX_LIMIT)
        lines += [
            "",
            f"**Verdict:** {label} ({verdict.flaky.confidence:.0%}) — {rationale}",
        ]
    if verdict.suggested_fix:
        fix = _safe_inline(verdict.suggested_fix, limit=_SUGGESTED_FIX_LIMIT)
        lines += ["", f"**Suggested fix:** {fix}"]
    return f"{MARKER}\n" + "\n".join(lines) + _FOOTER
