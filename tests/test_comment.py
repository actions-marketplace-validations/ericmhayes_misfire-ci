"""Unit tests for `comment.render_comment`, including the flaky line."""

from __future__ import annotations

from misfire.comment import render_comment
from misfire.schema import (
    FailureCategory,
    FlakyAssessment,
    FlakyClassification,
    Verdict,
)


def _verdict(**over) -> Verdict:
    base = dict(
        root_cause="Assertion changed 'active' -> 'pending'.",
        category=FailureCategory.TEST_ASSERTION,
        suggested_fix=None,
        confidence=0.8,
    )
    base.update(over)
    return Verdict(**base)


def test_renders_core_fields_and_footer() -> None:
    out = render_comment(_verdict())
    assert "**Root cause:**" in out
    assert "`test_assertion`" in out
    assert "**Confidence:** 80%" in out
    assert "advisory only" in out  # footer


def test_omits_flaky_line_when_no_test_implicated() -> None:
    out = render_comment(_verdict(flaky=None))
    assert "**Verdict:**" not in out


def test_renders_flaky_verdict_line() -> None:
    out = render_comment(
        _verdict(
            flaky=FlakyAssessment(
                classification=FlakyClassification.LIKELY_FLAKY,
                confidence=0.62,
                rationale="Failed on 5 of 20 recent runs built from other commits.",
            )
        )
    )
    assert "**Verdict:** 🟡 Likely flaky (62%)" in out
    assert "other commits" in out


def test_renders_real_verdict_line() -> None:
    out = render_comment(
        _verdict(
            flaky=FlakyAssessment(
                classification=FlakyClassification.REAL,
                confidence=0.9,
                rationale="Passed on every recent unrelated run.",
            )
        )
    )
    assert "🔴 Likely a real failure (90%)" in out
