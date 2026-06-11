"""Orchestrates stages. Each is optional and independent (--only)."""
from __future__ import annotations
import asyncio
from rich.console import Console

from .config import Config
from .context import RunContext
from .stages import explore, crawl, qa, journey, analyze, overview, script, storyboard

console = Console()


def run(cfg: Config, only: set[str] | None = None) -> RunContext:
    ctx = RunContext()
    console.rule(f"[bold]saascope[/] · run dir: {ctx.dir}")

    def enabled(name: str) -> bool:
        return name in only if only else cfg.stage_enabled(name)

    from .llm import LLMClient
    explore_client = LLMClient(cfg.explore_provider, cfg.explore_model)
    writer_client = LLMClient(cfg.llm_provider, cfg.llm_model)

    if enabled("explore"):
        console.print(f"[cyan]› explore[/] — journey agent "
                      f"({cfg.get('exploration','engine', default='owned')}, "
                      f"decisions: {cfg.explore_provider}·{cfg.explore_model})")
        asyncio.run(explore.run(cfg, ctx, explore_client))
    if enabled("crawl"):
        console.print("[cyan]› crawl[/] — inventory + tech detection")
        asyncio.run(crawl.run(cfg, ctx))

    if any(enabled(s) for s in ("qa", "journey", "analyze", "overview", "script")):
        console.print(f"[dim]writer LLM: {cfg.llm_provider} · {cfg.llm_model}[/]")
    if enabled("journey"):
        console.print("[magenta]› journey[/] — step-by-step user walkthrough")
        journey.run(cfg, ctx, writer_client)
    if enabled("qa"):
        console.print("[magenta]› qa[/] — bug & usability report")
        qa.run(cfg, ctx, writer_client)
    if enabled("analyze"):
        console.print("[green]› analyze[/] — audit report")
        analyze.run(cfg, ctx, writer_client)
    if enabled("overview"):
        console.print("[green]› overview[/] — SaaS overview report")
        overview.run(cfg, ctx, writer_client)
    if enabled("script"):
        console.print("[green]› script[/] — demo/onboarding script")
        script.run(cfg, ctx, writer_client)
    if enabled("storyboard"):
        console.print("[blue]› storyboard[/] — editor kit (shotlist.json + storyboard.html)")
        storyboard.run(cfg, ctx, writer_client)

    gallery = ctx.store.write_gallery()
    _maybe_export(cfg, ctx)
    console.rule("[bold green]done")
    console.print(f"Artifacts: {ctx.dir}")
    console.print(f"Screenshots: {len(ctx.store.records())} · {gallery}")
    return ctx


def _maybe_export(cfg: Config, ctx: RunContext) -> None:
    import shutil, subprocess
    formats = [f for f in cfg.get("output", "formats", default=["md"]) if f != "md"]
    if not formats or not shutil.which("pandoc"):
        if formats:
            console.print("[yellow]pandoc not found; skipping pdf/docx export[/]")
        return
    for md in ctx.report_dir.glob("*.md"):
        for fmt in formats:
            try:
                subprocess.run(["pandoc", str(md), "-o", str(md.with_suffix(f'.{fmt}'))],
                               check=True)
            except subprocess.CalledProcessError:
                console.print(f"[yellow]  pandoc failed for {md.name}[/]")
