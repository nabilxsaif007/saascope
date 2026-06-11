"""Stage 5 — product overview (Claude)."""
from __future__ import annotations
from ..config import Config
from ..context import RunContext
from ._shared import load_prompt, gather_evidence


def run(cfg: Config, ctx: RunContext, client) -> None:
    system = load_prompt("product_overview.md")
    evidence, imgs = gather_evidence(cfg, ctx)
    user = (
        "From the evidence below (and screenshots), write the product overview. "
        "If something (e.g. pricing) is not visible in the evidence, say so "
        "explicitly rather than inventing it.\n\n" + evidence
    )
    md = client.complete(system, user, images=imgs, max_tokens=6000)
    ctx.save_text("report/02_saas_overview.md", md)
