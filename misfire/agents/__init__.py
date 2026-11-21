"""Provider adapters. Each exposes the same `run(...)` entrypoint over the SHARED
tools, selected at runtime via `--provider` (see `misfire/providers.py`).

- claude.py  — the default adapter (Anthropic)
- openai.py  — the OpenAI adapter (also drives OpenAI-compatible endpoints)
"""
