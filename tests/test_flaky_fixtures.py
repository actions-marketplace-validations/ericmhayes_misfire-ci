"""Accuracy criterion: flaky-vs-real accuracy on a labeled fixture set.

The accuracy criterion requires the classifier to be right >=80% each way on >=10 known-real and
>=10 known-flaky failures. These fixtures carry a *human* ground-truth label
(what the failure actually was), set independently of the classifier's own rule,
and include deliberately hard cases the classifier is expected to miss — so the
80% bar measures something real instead of being trivially 100%.

Known blind spots encoded here (accepted trade-offs, see flaky.py):
  - REAL failure + one unrelated noisy failure in the window -> called FLAKY.
    The classifier leans flaky on any other-commit failure by design (never
    blame the diff for a test that fails elsewhere), so it over-calls flaky here.
  - Genuinely FLAKY test that, in a small sample window, happened to fail only on
    the current commit -> called REAL (not enough signal yet).
"""

from __future__ import annotations

from misfire.flaky import classify
from misfire.history import TestHistory
from misfire.schema import FlakyClassification

REAL = FlakyClassification.REAL
FLAKY = FlakyClassification.LIKELY_FLAKY


def _h(total: int, failures: int, other: int) -> TestHistory:
    return TestHistory("t", total_runs=total, failures=failures, failures_on_other_commits=other)


# (history, human ground-truth label, note). Ground truth = what the failure
# really was, NOT what the classifier outputs.
REAL_FIXTURES = [
    (_h(20, 1, 0), REAL, "clean 20-run history, fails only on this commit"),
    (_h(15, 1, 0), REAL, "clean 15-run history"),
    (_h(30, 1, 0), REAL, "clean 30-run history"),
    (_h(8, 1, 0), REAL, "smaller but clean window"),
    (_h(50, 1, 0), REAL, "long clean history, obvious regression"),
    (_h(12, 1, 0), REAL, "clean 12-run history"),
    (_h(25, 1, 0), REAL, "clean 25-run history"),
    (_h(10, 1, 0), REAL, "clean 10-run history"),
    (_h(40, 1, 0), REAL, "long clean history"),
    (_h(18, 1, 0), REAL, "clean 18-run history"),
    # Hard: a real regression that coincided with one unrelated flaky blip.
    (_h(20, 2, 1), REAL, "HARD: real regression + 1 noisy unrelated failure"),
    (_h(30, 3, 1), REAL, "HARD: real regression + 1 noisy unrelated failure"),
]

FLAKY_FIXTURES = [
    (_h(20, 8, 7), FLAKY, "fails constantly across commits"),
    (_h(30, 6, 5), FLAKY, "intermittent across many commits"),
    (_h(20, 6, 5), FLAKY, "fails on 5 unrelated commits"),
    (_h(40, 4, 4), FLAKY, "rarely flaky but always on other commits"),
    (_h(15, 3, 3), FLAKY, "flaky across unrelated commits"),
    (_h(25, 5, 4), FLAKY, "intermittent flaky"),
    (_h(50, 10, 9), FLAKY, "chronically flaky"),
    (_h(10, 2, 2), FLAKY, "flaky in a short window"),
    (_h(20, 5, 5), FLAKY, "half its failures on unrelated commits"),
    (_h(12, 2, 2), FLAKY, "flaky on unrelated commits"),
    (_h(18, 4, 3), FLAKY, "flaky across commits"),
    # Hard: genuinely flaky, but this small window only caught a current-commit fail.
    (_h(6, 1, 0), FLAKY, "HARD: flaky test, tiny window with no unrelated failure yet"),
]


def _accuracy(fixtures) -> float:
    hits = sum(1 for h, label, _ in fixtures if classify(h).classification is label)
    return hits / len(fixtures)


def test_real_fixtures_meet_accuracy_bar() -> None:
    assert len(REAL_FIXTURES) >= 10
    acc = _accuracy(REAL_FIXTURES)
    assert acc >= 0.80, f"real accuracy {acc:.0%} below the 80% bar"


def test_flaky_fixtures_meet_accuracy_bar() -> None:
    assert len(FLAKY_FIXTURES) >= 10
    acc = _accuracy(FLAKY_FIXTURES)
    assert acc >= 0.80, f"flaky accuracy {acc:.0%} below the 80% bar"
