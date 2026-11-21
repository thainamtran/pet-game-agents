"""Runtime settings from the environment, a local .env file, and CLI overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Mode = Literal["auto", "mock", "llm"]

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file without overwriting existing env vars."""
    env_path = path or Path.cwd() / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mode: Mode
    openai_api_key: str | None
    openai_base_url: str
    openai_model: str
    species: str
    theme: str
    auto_approve: bool
    max_retries: int
    output_dir: Path

    @classmethod
    def from_env(cls, **overrides: object) -> "Settings":
        load_dotenv()
        mode = str(overrides.get("mode") or _get("LLM_MODE", "auto") or "auto").lower()
        if mode not in {"auto", "mock", "llm"}:
            raise ValueError(f"Invalid LLM_MODE / --mode: {mode!r} (use auto, mock, or llm)")
        key = overrides.get("openai_api_key", _get("OPENAI_API_KEY") or None)
        if isinstance(key, str):
            key = key.strip() or None
        auto = overrides.get("auto_approve")
        if auto is None:
            auto = _get("PET_GAME_AUTO_APPROVE", "false").lower() in {"1", "true", "yes", "on"}
        max_retries = overrides.get("max_retries")
        if max_retries is None:
            raw = _get("PET_GAME_MAX_RETRIES", "3") or "3"
            max_retries = int(raw)
        output = overrides.get("output_dir") or _get("PET_GAME_OUTPUT_DIR", "output") or "output"
        output_dir = Path(output).expanduser()
        if not output_dir.is_absolute():
            output_dir = (Path.cwd() / output_dir).resolve()
        return cls(
            mode=mode,  # type: ignore[arg-type]
            openai_api_key=key if isinstance(key, str) or key is None else None,
            openai_base_url=str(
                overrides.get("openai_base_url")
                or _get("OPENAI_BASE_URL", "https://api.openai.com/v1")
                or "https://api.openai.com/v1"
            ).rstrip("/"),
            openai_model=str(
                overrides.get("openai_model")
                or _get("OPENAI_MODEL", "gpt-4o-mini")
                or "gpt-4o-mini"
            ),
            species=str(
                overrides.get("species") or _get("PET_GAME_SPECIES", "cat") or "cat"
            ).strip().lower(),
            theme=str(
                overrides.get("theme")
                or _get("PET_GAME_THEME", "cozy backyard companion")
                or "cozy backyard companion"
            ).strip(),
            auto_approve=bool(auto),
            max_retries=int(max_retries),
            output_dir=output_dir,
        )

    def resolved_mode(self) -> Literal["mock", "llm"]:
        if self.mode == "llm":
            return "llm"
        if self.mode == "mock":
            return "mock"
        return "llm" if self.openai_api_key else "mock"

    def require_llm_key(self) -> str:
        if not self.openai_api_key:
            raise RuntimeError(
                "LLM mode was requested but OPENAI_API_KEY is not set. "
                "Use --mock for offline mode, or set OPENAI_API_KEY (see .env.example)."
            )
        return self.openai_api_key
