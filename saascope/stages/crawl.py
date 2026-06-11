"""Stage 2 — crawl inventory + tech detection via Crawl4AI.

Cheap pass that enumerates reachable pages -> markdown, and inspects script
sources / response signals to detect third-party tech and integrations.
"""
from __future__ import annotations
import re
from pathlib import Path

from ..config import Config
from ..context import RunContext

# Minimal vendor signature map (extend freely).
TECH_SIGNATURES = {
    "Google Analytics": [r"google-analytics\.com", r"gtag/js", r"googletagmanager"],
    "Segment": [r"cdn\.segment\.com"],
    "Stripe": [r"js\.stripe\.com"],
    "Intercom": [r"widget\.intercom\.io"],
    "HubSpot": [r"js\.hs-scripts\.com", r"hubspot"],
    "Mixpanel": [r"cdn\.mxpanel", r"mixpanel"],
    "Sentry": [r"browser\.sentry-cdn", r"sentry\.io"],
    "Cloudflare": [r"cloudflare"],
    "React": [r"react(\.production)?\.min\.js", r"__REACT_DEVTOOLS"],
    "Next.js": [r"/_next/"],
    "Vue": [r"vue(\.runtime)?\.min\.js"],
    "Amplitude": [r"amplitude"],
    "Datadog": [r"datadoghq", r"dd-rum"],
}


def _detect(html: str) -> list[str]:
    found = []
    for vendor, pats in TECH_SIGNATURES.items():
        if any(re.search(p, html, re.I) for p in pats):
            found.append(vendor)
    return sorted(set(found))


async def run(cfg: Config, ctx: RunContext) -> None:
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    except Exception as e:  # pragma: no cover
        ctx.save_text("crawl/SKIPPED.txt", f"crawl4ai not importable: {e}")
        return

    # Seed from explore's visited URLs if present, else the target.
    seeds = ctx.load_json("explore/visited_urls.json", default=[]) or [cfg.target_url]
    seeds = list(dict.fromkeys(seeds))[: int(cfg.get("crawl", "max_pages", default=60))]

    inventory: list[dict] = []
    all_tech: set[str] = set()

    async with AsyncWebCrawler() as crawler:
        for i, url in enumerate(seeds):
            try:
                run_cfg = CrawlerRunConfig(screenshot=False)
                result = await crawler.arun(url=url, config=run_cfg)
            except Exception as e:
                inventory.append({"url": url, "error": str(e)})
                continue

            md = getattr(result, "markdown", "") or ""
            html = getattr(result, "html", "") or ""
            tech = _detect(html)
            all_tech.update(tech)

            slug = re.sub(r"[^a-z0-9]+", "-", url.lower())[:60].strip("-") or f"page-{i}"
            ctx.save_text(f"crawl/pages/{i:03d}_{slug}.md", md[:20000])
            title = ""
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()
            inventory.append({
                "url": url,
                "title": title,
                "tech": tech,
                "chars": len(md),
            })

    ctx.save_json("crawl/inventory.json", inventory)
    ctx.save_json("crawl/tech_detected.json", sorted(all_tech))
