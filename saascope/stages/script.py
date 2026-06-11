"""Stage 6 — demo / onboarding video script (Claude)."""
from __future__ import annotations
from ..config import Config
from ..context import RunContext
from ._shared import load_prompt, gather_evidence


def run(cfg: Config, ctx: RunContext, client) -> None:
    system = load_prompt("demo_script.md")
    evidence, imgs = gather_evidence(cfg, ctx)
    user = (
        "Write a demo + onboarding video script. Map each scene to the captured "
        "screenshot filenames (and the Playwright video in capture/video/) so an "
        "editor can assemble it. Evidence:\n\n" + evidence
    )
    md = client.complete(system, user, images=imgs, max_tokens=6000)
    ctx.save_text("report/03_demo_video_script.md", md)
