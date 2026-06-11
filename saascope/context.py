"""RunContext: one timestamped directory per run, with helpers + screenshot store."""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any

from .store import ScreenshotStore


class RunContext:
    def __init__(self, root: str | Path = "runs"):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.dir = Path(root) / stamp
        for sub in ("explore", "crawl", "qa", "report", "screenshots"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        # Every screenshot from every stage lands here, indexed for future use.
        self.store = ScreenshotStore(self.dir / "screenshots")

    @property
    def explore_dir(self) -> Path: return self.dir / "explore"
    @property
    def crawl_dir(self) -> Path: return self.dir / "crawl"
    @property
    def capture_dir(self) -> Path: return self.dir / "capture"
    @property
    def qa_dir(self) -> Path: return self.dir / "qa"
    @property
    def report_dir(self) -> Path: return self.dir / "report"
    @property
    def storage_state(self) -> Path: return self.dir / "storage_state.json"

    def save_json(self, relpath: str, obj: Any) -> Path:
        p = self.dir / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=2, default=str))
        return p

    def save_text(self, relpath: str, text: str) -> Path:
        p = self.dir / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def load_json(self, relpath: str, default: Any = None) -> Any:
        p = self.dir / relpath
        return json.loads(p.read_text()) if p.exists() else default
