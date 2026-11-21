"""LLM access with an OpenAI-compatible HTTP client and a deterministic mock."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from .config import Settings


class LLMError(RuntimeError):
    """Raised when an LLM request fails or returns unusable output."""


def extract_json(text: str) -> Any:
    """Parse a JSON object from a raw model response (fences allowed)."""
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            return json.loads(stripped[start : end + 1])
        raise LLMError(f"Could not parse JSON from model output: {text[:400]!r}") from None


class LLMClient:
    """Thin chat-completions client (OpenAI and compatible providers)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        key = self.settings.require_llm_key()
        body: dict[str, Any] = {
            "model": self.settings.openai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.openai_base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"LLM HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {payload!r}") from exc

    def complete_json(self, system: str, user: str) -> Any:
        return extract_json(self.complete(system, user, json_mode=True))


def get_client(settings: Settings) -> LLMClient:
    return LLMClient(settings)
