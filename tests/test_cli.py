"""CLI wiring: provider selection, bring-your-own-key guard, PR resolution.

These patch the GitHub client and the provider dispatch so no network, no model,
and no real key are involved.
"""

from __future__ import annotations

import pytest

from misfire import cli


@pytest.fixture(autouse=True)
def _github_env(monkeypatch):
    # `explain` requires GitHub credentials (set automatically inside the Action).
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")


class _FakeClient:
    def __init__(self, resolved: int | None) -> None:
        self._resolved = resolved
        self.resolved_for: int | None = None

    def find_pr_number_for_run(self, run_id: int) -> int | None:
        self.resolved_for = run_id
        return self._resolved


def _recording_run(record: dict):
    def fake_run(run_id, pr_number, client, *, model=None, **kw):
        record["args"] = (run_id, pr_number)
        record["model"] = model
        return "BODY"

    return fake_run


def test_explain_resolves_pr_and_dispatches(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    client = _FakeClient(resolved=42)
    rec: dict = {}
    monkeypatch.setattr(cli, "_github_client", lambda: client)
    monkeypatch.setattr(cli.providers, "get_run", lambda name: _recording_run(rec))

    assert cli.main(["explain", "--run", "7"]) == 0
    assert client.resolved_for == 7
    assert rec["args"] == (7, 42)
    assert rec["model"] == "claude-opus-4-8"  # provider default when --model omitted


def test_explain_noops_when_no_pr(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    ran: list = []
    monkeypatch.setattr(cli, "_github_client", lambda: _FakeClient(resolved=None))
    monkeypatch.setattr(cli.providers, "get_run", lambda name: (lambda **k: ran.append(k)))

    assert cli.main(["explain", "--run", "7"]) == 0
    assert ran == []  # no PR → agent never runs


def test_explain_requires_key_byo(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    touched: list = []
    monkeypatch.setattr(cli, "_github_client", lambda: touched.append("gh"))

    assert cli.main(["explain", "--run", "7"]) == 2
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY is not set" in err
    assert "bring-your-own-key" in err
    assert touched == []  # bails before doing anything


def test_explain_openai_provider(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    rec: dict = {}
    picked: dict = {}
    monkeypatch.setattr(cli, "_github_client", lambda: _FakeClient(resolved=5))

    def fake_get_run(name):
        picked["name"] = name
        return _recording_run(rec)

    monkeypatch.setattr(cli.providers, "get_run", fake_get_run)

    rc = cli.main(["explain", "--run", "3", "--provider", "openai", "--model", "gpt-4o-mini"])
    assert rc == 0
    assert picked["name"] == "openai"
    assert rec["args"] == (3, 5)
    assert rec["model"] == "gpt-4o-mini"  # user-set model threaded through


def test_explain_openai_missing_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.main(["explain", "--run", "3", "--provider", "openai"]) == 2
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().err


def test_analyze_no_ai_needs_no_key(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    log = tmp_path / "ci.log"
    log.write_text("ModuleNotFoundError: No module named 'requests'\n")
    assert cli.main(["analyze", "--logs", str(log), "--no-ai"]) == 0
    assert "`dependency`" in capsys.readouterr().out
