"""ModelRouter — provider/model abstraction layer for Claude AI.

Architecture §7.1 model_router.py / §24.1:
- Manages ModelConfig for Claude model calls.
- Supports native tool-use detection (Claude-only feature).
- Routes different task types to appropriate model configurations.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class TaskType(str, Enum):
    planning = "planning"
    coding = "coding"
    reviewing = "reviewing"
    build_fix = "build_fix"
    general = "general"


@dataclass
class ModelConfig:
    provider: str          # "anthropic"
    model: str             # e.g. "claude-sonnet-4-5" or "claude-3-7-sonnet-20250219"
    api_key: str | None
    max_tokens: int = 8192
    temperature: float = 0.2
    supports_tool_use: bool = True  # True for Anthropic Claude models

    @property
    def is_claude(self) -> bool:
        """Check if this model is a Claude model that supports native tool-use."""
        return self.provider == "anthropic" and self.supports_tool_use


class ModelRouter:
    """Routes task types to the appropriate model config for Anthropic Claude."""

    def __init__(self, model: str | None = None) -> None:
        self._api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
        self._model: str = model or os.environ.get("MODEL_NAME", "claude-sonnet-4-5")
        self._provider: str = os.environ.get("MODEL_PROVIDER", "anthropic")
        self._tool_use_enabled: bool = os.environ.get("TOOL_USE_ENABLED", "true").lower() == "true"

        print(f"[ModelRouter] Model: {self._model} | Provider: {self._provider} | "
              f"Tool-use: {self._tool_use_enabled}")

    def set_model(self, model: str) -> None:
        """Dynamically switch the active model (e.g. on follow-up prompt or model selector change)."""
        if model and model.strip():
            self._model = model.strip()
            os.environ["MODEL_NAME"] = self._model
            os.environ["AI_MODEL"] = self._model
            print(f"[ModelRouter] Active model dynamically switched to: {self._model}")

    @property
    def supports_tool_use(self) -> bool:
        """Whether the current model supports Claude's native tool-use API."""
        return self._provider == "anthropic" and self._tool_use_enabled

    def route(self, task_type: TaskType = TaskType.general, model: str | None = None) -> ModelConfig:
        """Return the ModelConfig for the given task type.

        ``model`` overrides the startup MODEL_NAME so a model switch on a
        follow-up actually changes which engine the subsequent calls use.
        The caller is responsible for passing the session's current model
        (state.model_name).
        """
        temperature = {
            TaskType.planning: 0.3,
            TaskType.coding: 0.15,
            TaskType.reviewing: 0.1,
            TaskType.build_fix: 0.1,
            TaskType.general: 0.2,
        }.get(task_type, 0.2)

        # Higher token limits for tool-use mode (more back-and-forth)
        if self.supports_tool_use:
            max_tokens = {
                TaskType.planning: 8192,
                TaskType.coding: 16384,
                TaskType.reviewing: 4096,
                TaskType.build_fix: 8192,
                TaskType.general: 8192,
            }.get(task_type, 8192)
        else:
            max_tokens = {
                TaskType.planning: 4096,
                TaskType.coding: 8192,
                TaskType.reviewing: 2048,
                TaskType.build_fix: 4096,
                TaskType.general: 4096,
            }.get(task_type, 4096)

        env_max = os.environ.get("MAX_OUTPUT_TOKENS") or os.environ.get("AI_MAX_TOKENS")
        if env_max and env_max.isdigit():
            max_tokens = int(env_max)

        return ModelConfig(
            provider=self._provider,
            model=model or self._model,
            api_key=self._api_key,
            max_tokens=max_tokens,
            temperature=temperature,
            supports_tool_use=self._provider == "anthropic" and self._tool_use_enabled,
        )
