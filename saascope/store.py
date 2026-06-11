"""Screenshot store: persist EVERY screenshot from every stage, indexed for reuse.

- Dedupes by content hash (sha256) so re-visits don't bloat the store.
- Appends one JSON record per shot to manifest.jsonl (stage, url, title, label, ts).
- Generates a browsable gallery.html contact sheet.
The manifest is the durable index you query in future runs / other tooling.
"""
from __future__ import annotations
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Optional


class ScreenshotStore:
    def __init__(self, base: Path):
        self.dir = Path(base)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.dir / "manifest.jsonl"
        self._by_hash: dict[str, str] = {}
        for rec in self.records():
            self._by_hash[rec["sha256"]] = rec["file"]

    def add_bytes(self, data: bytes, *, stage: str, url: str = "",
                  title: str = "", label: str = "",
                  meta: Optional[dict] = None) -> dict:
        h = hashlib.sha256(data).hexdigest()
        dup = h in self._by_hash
        if dup:
            fname = self._by_hash[h]
        else:
            seq = len(self._by_hash)
            fname = f"{seq:04d}_{stage}_{h[:8]}.png"
            (self.dir / fname).write_bytes(data)
            self._by_hash[h] = fname
        rec = {"id": h[:12], "file": fname, "stage": stage, "url": url,
               "title": title, "label": label, "sha256": h, "dup": dup,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "meta": meta or {}}
        with self.manifest_path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec

    def add_file(self, path, **kw) -> dict:
        return self.add_bytes(Path(path).read_bytes(), **kw)

    def records(self) -> list[dict]:
        if not self.manifest_path.exists():
            return []
        return [json.loads(l) for l in self.manifest_path.read_text().splitlines() if l.strip()]

    def paths(self, stage: Optional[str] = None, limit: Optional[int] = None) -> list[Path]:
        seen, out = set(), []
        for r in self.records():
            if stage and r["stage"] != stage:
                continue
            if r["file"] in seen:
                continue
            seen.add(r["file"])
            out.append(self.dir / r["file"])
        return out[:limit] if limit else out

    def write_gallery(self) -> Path:
        seen, cards = set(), []
        for r in self.records():
            if r["file"] in seen:
                continue
            seen.add(r["file"])
            cap = html.escape(f'{r["stage"]} · {r.get("title") or r.get("label") or ""}')
            url = html.escape(r.get("url", ""))
            cards.append(
                f'<figure><img src="{r["file"]}" loading="lazy">'
                f'<figcaption>{cap}<br><a href="{url}">{url}</a></figcaption></figure>')
        style = ("<style>body{font:14px system-ui;margin:24px;background:#0b0b0c;color:#eee}"
                 "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}"
                 "figure{margin:0;background:#161618;border-radius:8px;overflow:hidden}"
                 "img{width:100%;display:block;border-bottom:1px solid #333}"
                 "figcaption{padding:8px;font-size:12px;color:#bbb;word-break:break-all}"
                 "a{color:#7aa2f7}</style>")
        doc = (f"<!doctype html><meta charset=utf-8><title>Screenshot store</title>{style}"
               f"<h1>Screenshots ({len(seen)})</h1><main>{''.join(cards)}</main>")
        p = self.dir / "gallery.html"
        p.write_text(doc)
        return p
