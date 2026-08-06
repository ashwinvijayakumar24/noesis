"""Per-node model selection for the draft-analysis pipeline.

Nine of the ten LLM call sites in this pipeline hardcode
``gpt-5.2-chat-latest``; only ``editor_pass`` picks a cheaper tier, and it does
so by hardcoding too. Nothing establishes *where* the quality cliff is, because
until this module there was no way to move one node onto a cheaper model
without moving all of them.

This is a measurement seam, not a feature. Every site keeps the model it has
today as its ``default``; with no environment override set, :func:`model_for`
is the identity function on that default. Turning a measured routing decision
into a shipped one means changing the ``default`` at the call site, which is a
separate, deliberate edit.

Usage
-----
::

    model=model_for("reviewer_panel", "gpt-5.2-chat-latest")

overridden by ``NOESIS_MODEL_REVIEWER_PANEL=gpt-5-mini`` in the environment.

Read at call time, never cached
-------------------------------
``os.getenv`` runs on every call rather than being captured at import. The eval
harness sweeps arms inside a single process, setting and clearing the variable
between arms; a module-level constant would freeze whichever arm happened to
import first and silently report it as all of them. This repo has already had
seven incidents of two different things sharing one identity, so the sweep
harness also folds the resolved assignment into its config hash -- see
``scripts/eval/cascade_arms.py``.

A blank or whitespace-only value is treated as unset, so ``FOO=`` in a ``.env``
means "default" rather than "route to the empty-string model".
"""

from __future__ import annotations

import os

#: Site keys wired to :func:`model_for`, and the model each uses when no
#: override is set. Exists so the sweep harness can assert it is routing a site
#: that actually reads the environment, rather than silently measuring the
#: control three times -- a typo in a site key would otherwise be invisible.
ROUTED_SITES: dict[str, str] = {
    "reviewer_panel": "gpt-5.2-chat-latest",
    "extract_claims": "gpt-5.2-chat-latest",
    "structural_checks": "gpt-5.2-chat-latest",
    "meta_reviewer": "gpt-5.2-chat-latest",
}


def env_var_for(site: str) -> str:
    """The environment variable that overrides ``site``."""
    return f"NOESIS_MODEL_{site.upper()}"


def model_for(site: str, default: str) -> str:
    """The model to use for ``site``; ``default`` unless overridden.

    ``default`` is passed in rather than looked up in :data:`ROUTED_SITES` so
    that the call site remains the single source of truth for what it runs in
    production. A reader at the call site sees the real model name without
    having to open this file.
    """
    override = os.getenv(env_var_for(site), "").strip()
    return override or default
