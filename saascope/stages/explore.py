"""Stage 1 — exploration. Default engine is the owned journey agent (Playwright +
LLM decision + coverage graph + safety guard). Set exploration.engine to
'browser-use' to use that instead (optional; subject to its API drift).

Either way the stage produces explore/journey.json (ordered steps), every step
screenshot in the store (stage='journey'), visited_urls.json, and the runtime
QA signals in qa/runtime_findings.json.
"""
from __future__ import annotations
from ..config import Config
from ..context import RunContext
from .. import agent


async def run(cfg: Config, ctx: RunContext, client=None) -> None:
    engine = cfg.get("exploration", "engine", default="owned")
    if engine == "browser-use":
        await _browser_use(cfg, ctx)
    else:
        await agent.run(cfg, ctx, client)


async def _browser_use(cfg: Config, ctx: RunContext) -> None:
    """Optional path. Adjust the marked lines per your installed version."""
    try:
        from browser_use import Agent
        from browser_use.llm import ChatAnthropic
    except Exception as e:  # pragma: no cover
        ctx.save_text("explore/SKIPPED.txt", f"browser-use unavailable: {e}")
        return
    bu = Agent(task=cfg.get("exploration", "goal", default="Explore the app."),
               llm=ChatAnthropic(model=cfg.explore_model))
    history = await bu.run(max_steps=int(cfg.get("exploration", "max_steps", default=60)))
    urls = []
    try:
        urls = list(dict.fromkeys(u for u in history.urls() if u))
    except Exception:
        pass
    ctx.save_json("explore/visited_urls.json", urls)
    ctx.save_json("explore/journey.json",
                  [{"index": i, "action": str(a)} for i, a in
                   enumerate(getattr(history, "model_actions", lambda: [])())])
