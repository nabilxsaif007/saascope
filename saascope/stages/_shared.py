"""Helpers shared by writer stages."""
from __future__ import annotations
from pathlib import Path

from ..config import Config
from ..context import RunContext


def load_prompt(name: str) -> str:
    return (Path(__file__).resolve().parent.parent / "prompts" / name).read_text()


def gather_evidence(cfg: Config, ctx: RunContext) -> tuple[str, list[Path]]:
    parts = [f"TARGET: {cfg.target_url}"]

    io = ctx.load_json("explore/io_map.json", default={})
    if io:
        parts.append("INPUTS (data goes in): " + ", ".join(
            f"{i.get('label','')}({i.get('type','')})" for i in io.get("inputs", [])[:60]))
        parts.append("APP API ENDPOINTS: " + ", ".join(
            e["endpoint"] for e in io.get("app_endpoints", [])[:80]))
        parts.append("THIRD-PARTY SERVICES: " + ", ".join(
            t["host"] for t in io.get("third_party_services", [])[:60]))
        parts.append("OUTPUTS (files/exports): " + ", ".join(
            (o.get("name") or o.get("url", "")) for o in io.get("outputs", [])[:40]))

    steps = ctx.load_json("explore/journey.json", default=[])
    if steps:
        parts.append("WALKTHROUGH (ordered, every screen/menu/modal/form):")
        for s in steps[:200]:
            parts.append(f"- step {s.get('index')} [{s.get('kind')}]: {s.get('action','')}"
                         f"  [{s.get('title','')}]")

    qa = ctx.load_json("qa/runtime_findings.json", default={})
    if qa:
        parts.append("QA SIGNALS: "
                     f"console_errors={len(qa.get('console_errors', []))}, "
                     f"page_errors={len(qa.get('page_errors', []))}, "
                     f"failed_requests={len(qa.get('failed_requests', []))}")

    max_imgs = int(cfg.get("output", "max_images_to_llm", default=16))
    imgs = ctx.store.paths(stage="journey", limit=max_imgs) or ctx.store.paths(limit=max_imgs)
    return "\n".join(parts), imgs
