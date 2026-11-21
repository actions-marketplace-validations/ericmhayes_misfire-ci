"""Local / offline analysis — no GitHub, no posting.

Powers `misfire analyze`: read logs (and optionally a diff) from a file or
stdin and either

  - run the same agentic diagnosis but **print** the advisory to stdout instead
    of posting it (needs an Anthropic key), or
  - `--no-ai`: a **deterministic, rule-based** summary with no model call — the
    offline fallback for when the LLM is unavailable or unwanted.

Nothing here touches the network: the AI path drives the normal agent loop over
a `_LocalClient` that serves the provided text and captures the rendered comment
instead of posting, with a no-history provider so the flaky verdict is simply
UNKNOWN (there is no run history to consult offline).
"""

from __future__ import annotations

import re

from .comment import MARKER
from .history import TestHistory
from .log_utils import truncate_logs
from .schema import FailureCategory
from .scrub import scrub_secrets

# Rule-based category guesses, most specific first. Heuristic — the AI path is
# the real diagnosis; this is the deterministic fallback.
_RULES: list[tuple[FailureCategory, re.Pattern]] = [
    (
        FailureCategory.DEPENDENCY,
        re.compile(
            r"ModuleNotFoundError|ImportError|No module named|could not find|"
            r"npm ERR!|E: Unable to locate|unresolved import|cannot find package",
            re.IGNORECASE,
        ),
    ),
    (
        FailureCategory.COMPILE_ERROR,
        re.compile(
            r"SyntaxError|cannot find symbol|compilation failed|compilation error|"
            r"error\[E\d+\]|\berror: expected|undefined reference",
            re.IGNORECASE,
        ),
    ),
    (
        FailureCategory.TIMEOUT,
        re.compile(r"\bTimeoutError\b|timed out|\bETIMEDOUT\b|deadline exceeded", re.IGNORECASE),
    ),
    (
        FailureCategory.TEST_ASSERTION,
        re.compile(r"AssertionError|\bFAILED\b|\bassert\b|expected .*\bgot\b", re.IGNORECASE),
    ),
    (
        FailureCategory.INFRASTRUCTURE,
        re.compile(
            r"Connection refused|OOMKilled|No space left|rate limit|"
            r"503 Service|could not connect|Temporary failure in name resolution",
            re.IGNORECASE,
        ),
    ),
]


def categorize(logs: str) -> FailureCategory:
    """Best-effort rule-based failure bucket (no LLM). UNKNOWN when nothing matches."""
    for category, pattern in _RULES:
        if pattern.search(logs):
            return category
    return FailureCategory.UNKNOWN


def summarize(logs: str, diff: str | None = None) -> str:
    """Deterministic offline summary: scrub, categorize, show the key log excerpt."""
    scrubbed = scrub_secrets(logs)
    excerpt = truncate_logs(scrubbed)
    category = categorize(scrubbed)
    lines = [
        "### 🔧 Misfire — offline failure summary (no AI)",
        "",
        f"**Category (heuristic):** `{category.value}`",
        "",
        "**Key log excerpt:**",
        "```",
        excerpt,
        "```",
    ]
    if diff:
        n = len(diff.splitlines())
        lines += ["", f"_Diff provided ({n} lines) — not analyzed without AI._"]
    return "\n".join(lines)


class _NoHistoryProvider:
    """History provider for offline mode: there is no run history, so UNKNOWN."""

    def get_history(self, test_id: str, *, current_sha: str | None = None) -> TestHistory:
        return TestHistory.empty(test_id)


class _LocalClient:
    """Stands in for GitHubClient in offline AI mode: serves provided text and
    captures the rendered advisory instead of posting it anywhere."""

    def __init__(self, logs: str, diff: str | None) -> None:
        self._logs = logs
        self._diff = diff if diff is not None else "(no diff provided)"
        self.captured: str | None = None

    def fetch_failing_logs(self, run_id: int) -> str:
        return self._logs

    def fetch_pr_diff(self, pr_number: int) -> str:
        return self._diff

    def upsert_pr_comment(self, pr_number: int, body: str, *, marker: str) -> str:
        self.captured = body
        return "(local analysis — not posted)"


def analyze_with_ai(
    logs: str,
    diff: str | None = None,
    *,
    provider: str = "claude",
    model: str | None = None,
    max_turns: int | None = None,
    token_budget: int | None = None,
    anthropic_client=None,
) -> str:
    """Run the agent over local text on the chosen provider; return the rendered
    advisory (not posted). The adapter is imported lazily, so `--no-ai` and the
    unused providers' SDKs/keys are never required just to import this module.
    """
    from . import providers

    run_fn = providers.get_run(provider)
    client = _LocalClient(logs, diff)
    kwargs: dict = {
        "model": providers.resolve_model(provider, model),
        "history_provider": _NoHistoryProvider(),
    }
    if max_turns is not None:
        kwargs["max_turns"] = max_turns
    if token_budget is not None:
        kwargs["token_budget"] = token_budget
    if anthropic_client is not None:  # test injection for the Claude adapter
        kwargs["anthropic_client"] = anthropic_client

    body = run_fn(0, 0, client, **kwargs)
    if body and MARKER in body:
        return body
    return body or "Misfire found nothing actionable in the provided logs."
