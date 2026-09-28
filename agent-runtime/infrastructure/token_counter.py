"""
Token counting utilities for prompt budget awareness.

Provides lightweight estimates (no tokenizer required) so prompt construction
can stay within model context windows without network calls.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.model_profile import ModelProfile


def estimate_tokens(text: str, chars_per_token: float = 3.8) -> int:
    """Estimate token count from character count.

    Uses empirical chars-per-token ratio for English/JSX code.
    Accurate within ±15% for typical prompt payloads.
    """
    if not text:
        return 0
    return max(1, int(len(text) / chars_per_token))


def compute_output_budget(
    prompt_text: str,
    system_text: str,
    profile: "ModelProfile",
) -> int:
    """Return how many output tokens are safely available given the prompt size.

    Raises ValueError if the combined input already exceeds 90% of the context window,
    which means we cannot safely call the model.
    """
    combined = prompt_text + system_text
    input_tokens = estimate_tokens(combined, profile.chars_per_token)
    max_input = int(profile.context_window * 0.90)

    if input_tokens > max_input:
        raise ValueError(
            f"[TokenCounter] Prompt too large: ~{input_tokens:,} tokens > "
            f"90% of {profile.context_window:,} context window. "
            f"Reduce history_context before calling the model."
        )

    return profile.usable_output_tokens


def select_context_tier(
    accumulated_chars: int,
    profile: "ModelProfile",
) -> int:
    """Return context tier (0-3) based on accumulated source code size.

    Tier 0: No history (first file)
    Tier 1: Full inline source — accumulated ≤ inline_context_char_limit
    Tier 2: Signature strip only — accumulated ≤ signature_context_char_limit
    Tier 3: Compact manifest (name + exports only) — beyond that
    """
    if accumulated_chars == 0:
        return 0
    if accumulated_chars <= profile.inline_context_char_limit:
        return 1
    if accumulated_chars <= profile.signature_context_char_limit:
        return 2
    return 3


def prompt_fits_safely(
    prompt_text: str,
    system_text: str,
    profile: "ModelProfile",
    safety_fraction: float = 0.70,
) -> bool:
    """Return True if the prompt fits within safety_fraction of the context window.

    safety_fraction=0.70 means we use at most 70% of the context window for input,
    leaving 30% headroom for output and KV cache.
    """
    combined = prompt_text + system_text
    input_tokens = estimate_tokens(combined, profile.chars_per_token)
    max_safe = int(profile.context_window * safety_fraction)
    return input_tokens <= max_safe
