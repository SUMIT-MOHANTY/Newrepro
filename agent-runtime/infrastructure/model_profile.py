"""
Model Capability Profile Registry.

Provides token budget awareness for any model connected to the pipeline.
Each ModelProfile describes a model's hard constraints so prompt construction
and file generation can stay within safe boundaries without hard-coded magic numbers.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ModelProfile:
    """Describes the token constraints of a specific LLM."""
    model_id: str
    context_window: int       # Max input tokens (e.g. 128_000 for deepseek v3.2)
    max_output_tokens: int    # Hard ceiling on output (e.g. 8_000 for deepseek v3.2)
    chars_per_token: float = 3.8   # Empirical: ~3.8 chars/token for English/JSX code
    output_reserve: int = 800      # Tokens reserved for model preamble/reasoning

    # ── Derived token budgets ──────────────────────────────────────────────────

    @property
    def usable_output_tokens(self) -> int:
        """Safe output token count after subtracting reasoning preamble reserve."""
        return max(self.max_output_tokens - self.output_reserve, 1_000)

    @property
    def max_file_chars(self) -> int:
        """Maximum characters a single generated file should contain.
        Derived from usable output tokens so the file always fits in one response."""
        return int(self.usable_output_tokens * self.chars_per_token)

    @property
    def inline_context_char_limit(self) -> int:
        """Max total chars of previous-file source to inject directly (Tier 1).
        Kept to 20% of context window to leave room for system prompt + directive."""
        return int(self.context_window * 0.20 * self.chars_per_token)

    @property
    def signature_context_char_limit(self) -> int:
        """Max total chars before switching from signature-strip to compact manifest (Tier 2→3).
        Kept to 40% of context window."""
        return int(self.context_window * 0.40 * self.chars_per_token)

    def describe(self) -> str:
        return (
            f"{self.model_id}: ctx={self.context_window // 1000}K "
            f"| out={self.max_output_tokens} "
            f"| file_budget={self.max_file_chars:,} chars"
        )


# ---------------------------------------------------------------------------
# Known model profiles — add new entries here as models are onboarded
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE = ModelProfile(
    model_id="default",
    context_window=128_000,
    max_output_tokens=8_000,
    chars_per_token=3.8,
    output_reserve=800,
)

KNOWN_PROFILES: dict[str, ModelProfile] = {
    # DeepSeek V3 / V3.2 — 128K context, 8K output (as observed from Bourntec logs)
    "deepseek":             ModelProfile("deepseek",              128_000, 8_000, 3.8, 800),
    "deepseek-v3":          ModelProfile("deepseek-v3",           128_000, 8_000, 3.8, 800),
    "deepseek-v3.2":        ModelProfile("deepseek-v3.2",         128_000, 8_000, 3.8, 800),
    # Kimi / Moonshot AI — 128K context
    "kimi":                 ModelProfile("kimi",                  128_000, 8_000, 3.8, 800),
    "moonshot":             ModelProfile("moonshot",              128_000, 8_000, 3.8, 800),
    # Claude Sonnet / Opus (Anthropic native or via Bourntec / AWS Bedrock)
    "claude":               ModelProfile("claude",                200_000, 8_096, 3.8, 600),
    "claude-sonnet-4-5":    ModelProfile("claude-sonnet-4-5",     200_000, 8_096, 3.8, 600),
    "claude-opus-4":        ModelProfile("claude-opus-4",         200_000, 8_096, 3.8, 600),
    "claude-3-5-sonnet":    ModelProfile("claude-3-5-sonnet",     200_000, 8_096, 3.8, 600),
    "claude-3-7-sonnet":    ModelProfile("claude-3-7-sonnet",     200_000, 16_000, 3.8, 600),
    # OpenAI GPT-4o / o-series
    "gpt-4o":               ModelProfile("gpt-4o",                128_000, 16_384, 3.8, 500),
    "gpt-4o-mini":          ModelProfile("gpt-4o-mini",           128_000, 16_384, 3.8, 500),
    # Llama / Mistral (common self-hosted)
    "llama-3.1-70b":        ModelProfile("llama-3.1-70b",         128_000, 8_000, 3.8, 800),
    "mistral-large":        ModelProfile("mistral-large",         128_000, 8_000, 3.8, 800),
}


def get_profile(model_id: str) -> ModelProfile:
    """Return the ModelProfile for a given model ID.

    Performs case-insensitive prefix matching so 'deepseek-chat-v3' resolves
    to 'deepseek-v3' rather than falling through to default.
    """
    if not model_id:
        return _DEFAULT_PROFILE

    model_lower = model_id.lower().strip()

    # Exact match first
    if model_lower in KNOWN_PROFILES:
        return KNOWN_PROFILES[model_lower]

    # Prefix match — longest prefix wins
    best_key = ""
    for key in KNOWN_PROFILES:
        if model_lower.startswith(key) and len(key) > len(best_key):
            best_key = key
    if best_key:
        return KNOWN_PROFILES[best_key]

    # Any substring match (e.g. "deepseek" anywhere in model_id)
    for key, profile in KNOWN_PROFILES.items():
        if key in model_lower:
            return profile

    return _DEFAULT_PROFILE
