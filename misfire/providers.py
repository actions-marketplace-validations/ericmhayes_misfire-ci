"""Provider registry — the AI backends Misfire can run on.

Each provider is an adapter in ``misfire/agents/`` exposing the same
``run(run_id, pr_number, client, *, max_turns, token_budget, history_provider)``
entrypoint over its own tool-calling loop. Selection is explicit (``--provider``
/ the Action's ``provider`` input); the default is Claude.

**Bring-your-own-key:** Misfire never supplies an API key. Each provider names
the environment variable that must hold *your* key, and every call is billed to
your account.

Adding a provider is just: write an adapter like ``agents/claude.py``, then add
an entry here. Adapter modules are imported lazily so a user only needs the
dependency for the provider they actually run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class Provider:
    name: str  # the --provider value
    module: str  # dotted path to the adapter module (exposes run())
    key_env: str  # env var holding the user's API key (BYO-key)
    label: str  # human-facing name
    default_model: str  # fallback model if the user doesn't set one
    extra: str | None = None  # optional pip extra that installs the SDK


# You pick the model at setup (the Action's `model` input / `misfire --model`).
# These defaults are only a fallback for the common case.
PROVIDERS: dict[str, Provider] = {
    "claude": Provider(
        name="claude",
        module="misfire.agents.claude",
        key_env="ANTHROPIC_API_KEY",
        label="Anthropic Claude",
        default_model="claude-opus-4-8",
    ),
    "openai": Provider(
        name="openai",
        module="misfire.agents.openai",
        key_env="OPENAI_API_KEY",
        label="OpenAI",
        default_model="gpt-4o",
        extra="openai",
    ),
}

DEFAULT_PROVIDER = "claude"


def names() -> list[str]:
    """Selectable provider names, for argparse choices."""
    return sorted(PROVIDERS)


def get(name: str) -> Provider:
    return PROVIDERS[name]


def get_run(name: str) -> Callable[..., str]:
    """Import the adapter lazily and return its run() — so unused providers'
    SDKs are never required."""
    return import_module(PROVIDERS[name].module).run


def resolve_model(name: str, model: str | None) -> str:
    """The user's chosen model, or the provider's fallback default."""
    return model or PROVIDERS[name].default_model
