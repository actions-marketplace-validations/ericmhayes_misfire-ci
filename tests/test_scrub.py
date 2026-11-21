"""Secret-scrubbing tests, with a hostile log fixture (Item 3).

Logs and the PR diff are attacker-influenceable, so `scrub.scrub_secrets` runs
over them before they reach the model. These prove known credential shapes and
high-entropy blobs are redacted while useful failure context survives.
"""

from __future__ import annotations

from misfire import tools
from misfire.scrub import PLACEHOLDER, scrub_secrets

HOSTILE_LOG = (
    "Running tests...\n"
    "export GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n"
    "ANTHROPIC_API_KEY=sk-ant-api03-AbCdEf0123456789AbCdEf0123456789AbCdEf\n"
    "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"
    "password: hunter2secretvalue\n"
    "Authorization: Bearer abcdef0123456789abcdef0123456789\n"
    "blob: Zm9vYmFyMTIzNDU2Nzg5MEFCQ0RFRkdISUpLTU5PUFFSU1R=\n"
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEA1234567890abcdef\n"
    "-----END RSA PRIVATE KEY-----\n"
    "tests/test_auth.py:42: AssertionError: expected 'active' got 'pending'\n"
)

_LEAKS = [
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "sk-ant-api03-AbCdEf0123456789",
    "AKIAIOSFODNN7EXAMPLE",
    "hunter2secretvalue",
    "abcdef0123456789abcdef0123456789",
    "Zm9vYmFy",
    "MIIEowIBAAKCAQEA",
]


def test_redacts_known_credentials() -> None:
    out = scrub_secrets(HOSTILE_LOG)
    for leak in _LEAKS:
        assert leak not in out, f"leaked: {leak}"
    assert PLACEHOLDER in out


def test_preserves_useful_context() -> None:
    out = scrub_secrets(HOSTILE_LOG)
    assert "tests/test_auth.py:42" in out
    assert "AssertionError" in out
    assert "expected 'active' got 'pending'" in out
    # Inline redactions keep their line (the failing tail stays where it was).
    assert "\ntests/test_auth.py:42" in out


def test_does_not_redact_paths_or_plain_words() -> None:
    text = "src/misfire/github_history_provider_implementation_longname.py failed"
    assert scrub_secrets(text) == text


def test_kv_keeps_key_redacts_value() -> None:
    out = scrub_secrets("api_key=SuperSecretValue123XYZabcEXTRA")
    assert out.startswith("api_key=")
    assert "SuperSecretValue123XYZabcEXTRA" not in out
    assert PLACEHOLDER in out


def test_redacts_provider_and_long_hex_tokens() -> None:
    secrets = [
        "glpat-ABCDEFghijkl1234567890",  # GitLab PAT
        "npm_" + "a" * 36,  # npm token
        "pypi-AgEIcHlwaS5vcmcABCDefgh1234",  # PyPI token
        "a" * 64,  # long lowercase-hex signing/webhook secret
    ]
    for secret in secrets:
        out = scrub_secrets(f"token: {secret}")
        assert secret not in out, secret
        assert PLACEHOLDER in out


def test_idempotent() -> None:
    once = scrub_secrets(HOSTILE_LOG)
    assert scrub_secrets(once) == once


def test_empty_input() -> None:
    assert scrub_secrets("") == ""


class _SecretClient:
    """Fake GitHub client whose logs/diff contain a secret."""

    def fetch_failing_logs(self, run_id: int) -> str:
        return "boom\nGITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n"

    def fetch_pr_diff(self, pr_number: int) -> str:
        return "+api_key=sk-ant-api03-AbCdEf0123456789AbCdEf0123456789AbCdEf\n"


def test_tool_boundary_scrubs_logs_and_diff() -> None:
    tools.bind(_SecretClient())
    logs = tools.get_failing_logs(1)
    diff = tools.get_pr_diff(1)
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in logs
    assert "sk-ant-api03" not in diff
    assert PLACEHOLDER in logs and PLACEHOLDER in diff
