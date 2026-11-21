# Security Policy

Misfire reads CI logs and PR diffs and sends them to an AI provider, so we take
security seriously.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately via GitHub's **[Private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)**
(the repository's **Security → Report a vulnerability** tab). We aim to
acknowledge within a few days and will coordinate a fix and disclosure with you.

If you can't use that channel, open a minimal public issue asking a maintainer to
reach out privately — **without** any vulnerability details — and we'll follow up.

## Supported versions

Misfire is pre-1.0; security fixes land on the latest released `0.x` version.
Please upgrade to the latest release before reporting.

## Scope & design notes

Misfire is **advisory-only** — its sole write action is one PR comment; it never
merges, blocks, or changes code. Relevant hardening already in place:

- **Secret scrubbing** (`misfire/scrub.py`) redacts credentials and high-entropy
  tokens from logs/diff before they reach the model (defense-in-depth behind
  GitHub's own log masking — not a guarantee).
- **Output sanitizing** — model-authored text is HTML-escaped, link/image- and
  marker-neutralized, and length-capped before rendering the comment.
- **Bring-your-own-key** — Misfire never ships or stores an API key; your key is
  supplied via your own secret and billed to your account.
- **Least privilege** — the Action needs only `contents: read`,
  `pull-requests: write`, `actions: read`.

Good examples of in-scope reports: a secret pattern that slips past scrubbing, a
sanitizer bypass that injects active content into the comment, or a way to make
Misfire take an action beyond posting one advisory comment.
