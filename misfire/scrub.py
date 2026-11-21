"""Best-effort secret scrubbing for text sent to the LLM.

GitHub masks *registered* secrets in Actions logs, but anything unregistered —
or the PR diff — is not covered. This is a defense-in-depth pass over the logs
and diff before they enter the model context (credibility / security): it
redacts well-known credential formats and long, high-entropy tokens.

It never reflows the text (line structure is preserved so truncation and the
model's reading stay intact) and fails safe — over-redaction only loses
context, under-redaction leaks secrets, so ambiguous random-looking blobs are
redacted. It is not a guarantee; it is a second line of defense behind GitHub's
own masking and good secret hygiene.
"""

from __future__ import annotations

import math
import re

PLACEHOLDER = "[REDACTED]"

# Known credential shapes, redacted wholesale.
_TOKEN_PATTERNS = [
    re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),  # Anthropic
    re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"),  # OpenAI project keys
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI
    re.compile(r"gh[opsur]_[A-Za-z0-9]{20,}"),  # GitHub tokens
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),  # GitHub fine-grained PAT
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),  # Google API key
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"),  # GitLab PAT
    re.compile(r"\bnpm_[A-Za-z0-9]{36}"),  # npm token
    re.compile(r"\bpypi-[A-Za-z0-9_\-]{16,}"),  # PyPI API token
    re.compile(r"(?i)\b[0-9a-f]{64,}\b"),  # long hex secret (webhook/signing keys)
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{16,}"),  # Bearer <token>
    # Authorization: <token>
    re.compile(r"(?i)\bauthorization\b\s*[:=]\s*[A-Za-z0-9._~+/=\-]{16,}"),
]

# key = value / key: value where the key name looks sensitive. Keeps the key and
# the separator, redacts only the value.
_KV_PATTERN = re.compile(
    r"(?i)([a-z0-9_.\-]*"
    r"(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret))"
    r"(\s*[:=]\s*)(['\"]?)([^\s'\"]{6,})\3"
)

# Candidate high-entropy tokens (base64/hex-ish) of meaningful length.
_HIGH_ENTROPY_CANDIDATE = re.compile(r"[A-Za-z0-9+/=_-]{32,}")
_ENTROPY_BITS_THRESHOLD = 4.0


def _shannon_bits(s: str) -> float:
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _redact_high_entropy(match: re.Match) -> str:
    token = match.group(0)
    # Random credentials mix cases and digits; file paths, hex hashes, and plain
    # words do not. Requiring all three classes keeps useful context readable
    # while still catching base64/mixed API keys.
    has_upper = any(c.isupper() for c in token)
    has_lower = any(c.islower() for c in token)
    has_digit = any(c.isdigit() for c in token)
    if has_upper and has_lower and has_digit and _shannon_bits(token) >= _ENTROPY_BITS_THRESHOLD:
        return PLACEHOLDER
    return token


def scrub_secrets(text: str) -> str:
    """Redact credentials and high-entropy tokens from `text`. Idempotent."""
    if not text:
        return text
    for pat in _TOKEN_PATTERNS:
        text = pat.sub(PLACEHOLDER, text)
    text = _KV_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{PLACEHOLDER}", text)
    text = _HIGH_ENTROPY_CANDIDATE.sub(_redact_high_entropy, text)
    return text
