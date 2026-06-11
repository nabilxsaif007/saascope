"""Stage — QA / bug report (runtime signals + LLM visual review of journey shots)."""
from __future__ import annotations
import json

from ..config import Config
from ..context import RunContext
from ._shared import load_prompt


def run(cfg: Config, ctx: RunContext, client) -> None:
    runtime = ctx.load_json("qa/runtime_findings.json", default={}) or {}
    summary = {
        "console_errors": len(runtime.get("console_errors", [])),
        "page_errors": len(runtime.get("page_errors", [])),
        "failed_requests": len(runtime.get("failed_requests", [])),
        "broken_links": len(runtime.get("broken_links", [])),
    }
    system = load_prompt("bug_report.md")
    imgs = ctx.store.paths(stage="journey",
                           limit=int(cfg.get("output", "max_images_to_llm", default=16)))
    user = (
        "Produce the bug & QA report. Combine the deterministic runtime signals "
        "below with a visual review of the attached journey screenshots (broken "
        "layouts, error states, overlapping/cut-off UI, empty states).\n\n"
        f"RUNTIME SIGNAL SUMMARY: {json.dumps(summary)}\n\n"
        f"RUNTIME FINDINGS (raw):\n{json.dumps(runtime, indent=2)[:12000]}"
    )
    md = client.complete(system, user, images=imgs, max_tokens=8000)
    ctx.save_text("report/04_bug_report.md", md)
    ctx.save_json("qa/findings.json", {"summary": summary, "runtime": runtime})
