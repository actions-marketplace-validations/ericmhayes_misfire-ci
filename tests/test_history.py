"""Unit tests for the flaky-history seam.

Covers the `TestHistory` model, the GitHub-backed provider's tally logic
(including the load-bearing "failed on *other* commits" signal), and the
`get_test_history` tool's model-facing formatting. All offline: the provider is
driven by a fake client, never the network.
"""

from __future__ import annotations

from misfire import tools
from misfire.github_client import RunRef
from misfire.github_history import GitHubTestHistoryProvider, _test_failed_in_logs
from misfire.history import TestHistory, TestHistoryProvider


class FakeClient:
    """Stand-in for GitHubClient: canned run metadata + per-run logs."""

    def __init__(self, current: RunRef, runs: list[RunRef], logs: dict[int, str]) -> None:
        self._current = current
        self._runs = runs
        self._logs = logs

    def get_run(self, run_id: int) -> RunRef:
        return self._current

    def list_workflow_runs(self, workflow_id: int, *, limit: int = 20) -> list[RunRef]:
        return self._runs

    def _download_run_logs(self, run_id: int) -> str:
        return self._logs.get(run_id, "")


# --- TestHistory model -------------------------------------------------------

def test_failure_rate_and_signal() -> None:
    h = TestHistory("t", total_runs=4, failures=1, failures_on_other_commits=1)
    assert h.failure_rate == 0.25
    assert h.has_signal

    empty = TestHistory.empty("t")
    assert empty.failure_rate == 0.0
    assert not empty.has_signal


# --- failure detection heuristic ---------------------------------------------

def test_detects_pytest_summary_and_header_but_not_passes() -> None:
    tid = "tests/test_auth.py::test_status"
    assert _test_failed_in_logs(f"FAILED {tid} - AssertionError", tid)
    assert _test_failed_in_logs("____ test_status ____\nboom", "test_status")
    # Mentioned without a failure marker (e.g. a collected/passed line) → not a failure.
    assert not _test_failed_in_logs(f"collected {tid}", tid)
    assert not _test_failed_in_logs("unrelated line", tid)


# --- provider tally ----------------------------------------------------------

def test_provider_isolates_other_branches_not_same_pr_commits() -> None:
    tid = "test_status"
    # The PR under test is branch "pr-42"; it has been pushed twice (runs 10, 11).
    # A failure on "main" (run 9) is the real flaky signal; the PR's own earlier
    # push (run 11) must NOT count as "other".
    current = RunRef(10, 900, "sha10", "failure", head_branch="pr-42")
    runs = [
        RunRef(10, 900, "sha10", "failure", head_branch="pr-42"),   # this push
        RunRef(11, 900, "sha11", "failure", head_branch="pr-42"),   # earlier push, SAME PR
        RunRef(9, 900, "sha9", "failure", head_branch="main"),      # other branch — flaky signal
        RunRef(8, 900, "sha8", "success", head_branch="main"),      # observed pass on main
    ]
    logs = {
        10: f"FAILED {tid} - AssertionError",
        11: f"FAILED {tid} - AssertionError",
        9: f"FAILED {tid} - AssertionError",
        8: f"PASSED {tid}",
    }
    provider: TestHistoryProvider = GitHubTestHistoryProvider(FakeClient(current, runs, logs), 10)
    h = provider.get_history(tid)

    assert h.total_runs == 4  # all four observed the test
    assert h.failures == 3
    # Only run 9 (on main) counts as "other" — the PR's own run 11 does not.
    assert h.failures_on_other_commits == 1


def test_provider_skips_runs_where_test_not_observed() -> None:
    tid = "tests/test_new.py::test_added"
    current = RunRef(10, 900, "sha10", "failure", head_branch="pr-1")
    runs = [
        RunRef(10, 900, "sha10", "failure", head_branch="pr-1"),  # test ran + failed
        RunRef(9, 900, "sha9", "success", head_branch="main"),    # old run — test didn't exist
    ]
    logs = {10: f"FAILED {tid}", 9: "ran some other tests, all green"}
    provider = GitHubTestHistoryProvider(FakeClient(current, runs, logs), 10)
    h = provider.get_history(tid)

    # Run 9 never mentions the test → not counted (no false "clean elsewhere" signal).
    assert h.total_runs == 1
    assert h.failures == 1
    assert h.failures_on_other_commits == 0


def test_provider_returns_empty_when_no_runs() -> None:
    current = RunRef(run_id=1, workflow_id=900, head_sha="head", conclusion="failure")
    provider = GitHubTestHistoryProvider(FakeClient(current, [], {}), 1)
    h = provider.get_history("whatever")
    assert not h.has_signal


def test_provider_caches_logs_per_run() -> None:
    current = RunRef(run_id=1, workflow_id=900, head_sha="head", conclusion="failure")
    runs = [RunRef(1, 900, "head", "failure")]
    calls = {"n": 0}

    class CountingLogs(FakeClient):
        def _download_run_logs(self, run_id: int) -> str:
            calls["n"] += 1
            return "FAILED t"

    provider = GitHubTestHistoryProvider(CountingLogs(current, runs, {}), 1)
    provider.get_history("t")
    provider.get_history("t")  # second lookup reuses the cached download
    assert calls["n"] == 1


# --- tool formatting ---------------------------------------------------------

class _StubProvider:
    def __init__(self, history: TestHistory) -> None:
        self._history = history

    def get_history(self, test_id: str, *, current_sha: str | None = None) -> TestHistory:
        return self._history


def test_tool_formats_signal_and_no_signal() -> None:
    tools.bind_history(_StubProvider(TestHistory("t", 4, 2, 1)))
    out = tools.get_test_history("t")
    assert "failed 2/4" in out and "50%" in out and "other than" in out

    tools.bind_history(_StubProvider(TestHistory.empty("t")))
    assert "No recent history" in tools.get_test_history("t")
