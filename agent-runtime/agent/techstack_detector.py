"""Tech stack detector — analyzes user prompt via a lightweight AI call to determine
whether a custom tech stack was requested or if the default React+Vite+Tailwind
scaffold should be used.
"""
from __future__ import annotations

import json
import re
from typing import Any, TypedDict


class TechStackDecision(TypedDict):
    is_custom: bool
    stack: str
    reason: str


DEFAULT_DECISION: TechStackDecision = {
    "is_custom": False,
    "stack": "react_vite_tailwind",
    "reason": "Default React 18 + Vite + Tailwind CSS SPA scaffold",
}

DETECTOR_SYSTEM_PROMPT = """You are a technical analyzer for an autonomous coding runtime.
Analyze the user's prompt to determine if they EXPLICITLY requested a specific, non-default tech stack, framework, backend, or language.

DEFAULT ENVIRONMENT: React 18 + Vite + Tailwind CSS (SPA)
Treat as DEFAULT (is_custom = false, stack = "react_vite_tailwind") if the prompt:
- Does not specify any framework or technology.
- Requests a "web app", "prototype", "portal", "dashboard", "tool", "system".
- Mentions React, Vite, or Tailwind CSS.

CUSTOM STACK:
Treat as CUSTOM (is_custom = true) ONLY if the user EXPLICITLY demands a different framework, backend, or language:
- Next.js / Nuxt.js / Remix / Astro
- Vue.js / Svelte / Angular / Solid.js
- Backend runtimes: Python (FastAPI / Flask / Django), Node.js (Express / NestJS), Go, Rust, Java
- Pure Vanilla JS / HTML / CSS without React

Respond with a JSON object ONLY:
{
  "is_custom": boolean,
  "stack": string,
  "reason": string
}"""


def detect_techstack(prompt: str, llm_client: Any = None, model: str = "") -> TechStackDecision:
    """Analyze prompt to determine whether a custom tech stack is requested."""
    if not prompt or not prompt.strip():
        return dict(DEFAULT_DECISION)

    prompt_lower = prompt.lower()

    # Fast heuristic check for obvious custom frameworks
    custom_keywords = [
        "next.js", "nextjs", "nuxt", "remix", "astro",
        "vue.js", "vue 3", "vuejs", "svelte", "sveltekit", "angular", "solid.js",
        "fastapi", "flask", "django", "express.js", "nestjs",
        "python backend", "golang", "rust web", "vanilla js",
    ]
    has_custom_keyword = any(k in prompt_lower for k in custom_keywords)

    # If no LLM client available, use heuristic
    if not llm_client or not hasattr(llm_client, "call_ai"):
        if has_custom_keyword:
            for kw in custom_keywords:
                if kw in prompt_lower:
                    return {
                        "is_custom": True,
                        "stack": kw.replace(" ", "_"),
                        "reason": f"Detected explicit tech stack keyword: {kw}",
                    }
        return dict(DEFAULT_DECISION)

    detection_prompt = (
        f"{DETECTOR_SYSTEM_PROMPT}\n\n"
        f"USER PROMPT:\n\"\"\"{prompt[:1500]}\"\"\"\n\n"
        "Return the JSON object:"
    )

    try:
        response = llm_client.call_ai(
            detection_prompt,
            tools=[],
            model=model,
            max_tokens=500,
        )
        raw_text = ""
        if hasattr(response, "content") and isinstance(response.content, str):
            raw_text = response.content
        elif hasattr(response, "text") and isinstance(response.text, str):
            raw_text = response.text
        elif hasattr(response, "raw_response") and isinstance(response.raw_response, str):
            raw_text = response.raw_response
        elif isinstance(response, str):
            raw_text = response

        # Parse JSON from response
        clean_json = raw_text.strip()
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean_json, re.DOTALL)
        if match:
            clean_json = match.group(0)
        elif "{" in clean_json and "}" in clean_json:
            clean_json = clean_json[clean_json.find("{"):clean_json.rfind("}") + 1]

        data = json.loads(clean_json)
        is_custom = bool(data.get("is_custom", False))
        stack = str(data.get("stack", "react_vite_tailwind")).strip()
        reason = str(data.get("reason", "")).strip()

        return {
            "is_custom": is_custom,
            "stack": stack if is_custom else "react_vite_tailwind",
            "reason": reason or ("Custom stack detected" if is_custom else "Default React+Tailwind SPA"),
        }
    except Exception as exc:
        print(f"[TechStackDetector] Warning: Detection call failed ({exc}), falling back to heuristic.")
        if has_custom_keyword:
            for kw in custom_keywords:
                if kw in prompt_lower:
                    return {
                        "is_custom": True,
                        "stack": kw.replace(" ", "_"),
                        "reason": f"Heuristic detected keyword: {kw}",
                    }
        return dict(DEFAULT_DECISION)
