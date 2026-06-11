"""Config loading: YAML overlaid with environment for secrets."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml
from dotenv import load_dotenv

load_dotenv()


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("env:"):
        var = value[4:]
        resolved = os.environ.get(var)
        if resolved is None:
            raise RuntimeError(f"Config references env:{var} but it is not set.")
        return resolved
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


@dataclass
class Config:
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        return cls(raw=_resolve_env(yaml.safe_load(Path(path).read_text())))

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    @property
    def target_url(self) -> str: return self.raw["target_url"]
    @property
    def login_url(self) -> str: return self.raw.get("login_url", self.target_url)

    # LLM — provider-agnostic, with sensible fallbacks ----------------------
    @property
    def llm_provider(self) -> str:
        return self.get("llm", "provider", default="anthropic")
    @property
    def llm_model(self) -> str:
        return self.get("llm", "model", default=self.raw.get("model", "claude-opus-4-8"))
    @property
    def explore_provider(self) -> str:
        return self.get("llm", "explore_provider", default=self.llm_provider)
    @property
    def explore_model(self) -> str:
        return self.get("llm", "explore_model",
                        default=self.raw.get("explore_model", self.llm_model))
    @property
    def model(self) -> str:  # back-compat alias
        return self.llm_model

    def stage_enabled(self, name: str) -> bool:
        return bool(self.get("stages", name, default=False))
