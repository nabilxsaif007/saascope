"""User-journey walkthrough: complete, annotated, with ins/outs as first-class.

Each step shows the annotated screenshot (badge+box on the element acted on),
a caption, and an "under the hood" line with the network the action fired and
any outputs (downloads). Plus an Inputs & Outputs summary of everything that
crosses the SaaS boundary.
"""
from __future__ import annotations
import html

from ..config import Config
from ..context import RunContext
from ._shared import load_prompt


def _net_line(step: dict) -> str:
    bits = []
    for c in step.get("network", [])[:6]:
        tag = "↗" if c["origin"] == "third_party" else "→"
        bits.append(f'{tag} {c["method"]} {c["path"]} ({c["status"]})')
    for o in step.get("outputs", []):
        bits.append(f'⬇ {o.get("name") or o.get("url","output")}')
    return " · ".join(bits)


def _narrate(client, cfg, ctx, steps):
    if client is None:
        return {}
    batch = int(cfg.get("journey", "caption_batch", default=6))
    system = load_prompt("journey_caption.md")
    shots = [s for s in steps if s.get("screenshot")]
    caps = {}
    for i in range(0, len(shots), batch):
        chunk = shots[i:i + batch]
        imgs = [ctx.store.dir / s["screenshot"] for s in chunk]
        listing = "\n".join(
            f'STEP {s["index"]}: kind={s.get("kind")} action="{s.get("action","")}" '
            f'title="{s.get("title","")}" net="{_net_line(s)}"' for s in chunk)
        user = ("For each STEP and its attached screenshot (same order), write a 1-2 "
                "sentence caption: what the user did / what this screen takes in or "
                "puts out, and what is shown. Return ONLY JSON {step:caption}.\n\n" + listing)
        try:
            for k, v in client.complete_json(system, user, images=imgs, max_tokens=2000).items():
                caps[int(k)] = v
        except Exception:
            pass
    return caps


def _io_section_md(io: dict) -> list[str]:
    out = ["## Everything In & Out of the SaaS\n"]
    ins = io.get("inputs", [])
    out.append(f"**Inputs ({len(ins)})** — where data goes in:")
    out += [f"- {html.escape(i.get('label',''))} ({i.get('type','')})" for i in ins[:60]] or ["- none detected"]
    eps = io.get("app_endpoints", [])
    out.append(f"\n**App API calls ({len(eps)})** — what the app sends to its own backend:")
    out += [f"- `{e['endpoint']}` ×{e['count']}" for e in eps[:80]] or ["- none observed"]
    tp = io.get("third_party_services", [])
    out.append(f"\n**Third-party services ({len(tp)})** — external integrations contacted:")
    out += [f"- {t['host']} ×{t['count']}" for t in tp[:60]] or ["- none observed"]
    outs = io.get("outputs", [])
    out.append(f"\n**Outputs ({len(outs)})** — files/exports produced:")
    out += [f"- {html.escape(o.get('name') or o.get('url',''))}" for o in outs[:40]] or ["- none observed"]
    return out


def run(cfg: Config, ctx: RunContext, client) -> None:
    steps = ctx.load_json("explore/journey.json", default=[]) or []
    io = ctx.load_json("explore/io_map.json", default={}) or {}
    caps = _narrate(client, cfg, ctx, steps)
    target = cfg.target_url

    # ---------- Markdown ----------
    md = [f"# User Journey — {target}\n",
          f"Complete annotated walkthrough · {len(steps)} steps.\n"]
    md += _io_section_md(io)
    md.append("\n---\n\n## Step-by-step\n")
    for s in steps:
        idx = s["index"]
        tag = {"screen": "🖥", "input_map": "⌨", "action": "▸"}.get(s.get("kind"), "▸")
        md.append(f"### {tag} Step {idx} — {s.get('action','')}")
        if s.get("title") or s.get("screen_url"):
            md.append(f"*{s.get('title','')}* · `{s.get('screen_url','')}`")
        if s.get("screenshot"):
            md.append(f"\n![Step {idx}](../screenshots/{s['screenshot']})\n")
        if s.get("result_screenshot"):
            md.append(f"_result:_\n\n![Step {idx} result](../screenshots/{s['result_screenshot']})\n")
        cap = caps.get(idx) or ""
        if cap:
            md.append(cap)
        if s.get("kind") == "input_map" and s.get("inputs"):
            md.append("Inputs: " + ", ".join(
                f"{html.escape(i['label'])} ({i['type']})" for i in s["inputs"][:20]))
        nl = _net_line(s)
        if nl:
            md.append(f"\n*Under the hood:* {nl}")
        md.append("")
    ctx.save_text("report/00_user_journey.md", "\n".join(md))

    # ---------- HTML ----------
    cards = []
    for s in steps:
        idx = s["index"]
        cap = html.escape(caps.get(idx) or "")
        nl = html.escape(_net_line(s))
        img = (f'<img src="../screenshots/{s["screenshot"]}" loading="lazy">'
               if s.get("screenshot") else "")
        if s.get("result_screenshot"):
            img += f'<img src="../screenshots/{s["result_screenshot"]}" loading="lazy" class="res">' 
        net = f'<code class="net">{nl}</code>' if nl else ""
        cards.append(f'<section><div class="n">Step {idx} · {html.escape(s.get("kind",""))}</div>'
                     f'<h3>{html.escape(s.get("action",""))}</h3>{img}'
                     f'<p>{cap}</p>{net}'
                     f'<a href="{html.escape(s.get("screen_url",""))}">{html.escape(s.get("screen_url",""))}</a></section>')
    style = ("<style>body{font:15px system-ui;max-width:920px;margin:24px auto;padding:0 16px;"
             "background:#0b0b0c;color:#eee}section{margin:0 0 40px;border-bottom:1px solid #222;"
             "padding-bottom:24px}.n{color:#ff3b6b;font-weight:600;font-size:12px}h3{margin:4px 0 12px}"
             "img{width:100%;border-radius:8px;border:1px solid #333}img.res{margin-top:8px;opacity:.95}.net{display:block;margin-top:8px;"
             "color:#9ece6a;font-size:12px;white-space:pre-wrap}a{color:#7aa2f7;font-size:12px;"
             "word-break:break-all}</style>")
    doc = (f"<!doctype html><meta charset=utf-8><title>User Journey</title>{style}"
           f"<h1>User Journey — {html.escape(target)}</h1>{''.join(cards)}")
    ctx.save_text("report/00_user_journey.html", doc)
