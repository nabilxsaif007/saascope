"""Stage 4 — audit report (Claude)."""
from __future__ import annotations
from ..config import Config
from ..context import RunContext
from ._shared import load_prompt, gather_evidence


def run(cfg: Config, ctx: RunContext, client) -> None:
    system = load_prompt("audit_report.md")
    evidence, imgs = gather_evidence(cfg, ctx)
    user = (
        "Using ALL the evidence below (and the attached screenshots), produce the "
        "structured SaaS audit report.\n\n" + evidence
    )
    md = client.complete(system, user, images=imgs, max_tokens=12000)
    ctx.save_text("report/01_audit_report.md", md)
