"""Storyboard stage — turns the captured stills + clips into an editor kit.

Deterministic (no LLM). Produces, in `video/`:
  - shotlist.json    machine-readable shot list the editor/pipeline works from:
                     ordered shots → annotated + clean frame paths, highlight
                     rect, caption, network/outputs, clip name, timecode,
                     suggested duration; plus per-clip info and reset-cut spans.
  - storyboard.html  flippable visual storyboard: each step as annotated still |
                     clean still, with action, screen, clip + timecode, duration.
"""
from __future__ import annotations
import html

from ..config import Config
from ..context import RunContext

_DEFAULT_TAIL_MS = 3500


def _caption(s: dict) -> str:
    if s.get("kind") == "input_map":
        ins = ", ".join(f'{i["label"]} ({i["type"]})' for i in s.get("inputs", [])[:8])
        return f"Inputs on this screen: {ins}" if ins else "Inputs on this screen"
    bits = [s.get("action", "")]
    net = s.get("network", [])
    if net:
        ep = net[0]
        bits.append(f'fires {ep["method"]} {ep["path"]}'
                    + (" (third-party)" if ep["origin"] == "third_party" else ""))
    for o in s.get("outputs", []):
        bits.append(f'produces {o.get("name") or "a download"}')
    return " — ".join([b for b in bits if b])


def _net_line(s: dict) -> str:
    out = []
    for c in s.get("network", [])[:5]:
        tag = "↗" if c["origin"] == "third_party" else "→"
        out.append(f'{tag} {c["method"]} {c["path"]} ({c["status"]})')
    for o in s.get("outputs", []):
        out.append(f'⬇ {o.get("name") or o.get("url", "output")}')
    return " · ".join(out)


def _durations(steps: list[dict]) -> dict[int, int]:
    """Suggested per-shot duration from the gap to the next shot in the same clip."""
    by_clip: dict[str, list[dict]] = {}
    for s in steps:
        by_clip.setdefault(s.get("clip", ""), []).append(s)
    dur: dict[int, int] = {}
    for _, group in by_clip.items():
        group = sorted(group, key=lambda x: x.get("t_ms", 0))
        for i, s in enumerate(group):
            if i + 1 < len(group):
                d = max(1200, group[i + 1]["t_ms"] - s["t_ms"])
            else:
                d = _DEFAULT_TAIL_MS
            dur[s["index"]] = int(d)
    return dur


def _tc(ms: int) -> str:
    s, m = ms / 1000.0, 0
    m, s = divmod(s, 60)
    return f"{int(m):02d}:{s:05.2f}"


def run(cfg: Config, ctx: RunContext, client=None) -> None:
    steps = ctx.load_json("explore/journey.json", default=[]) or []
    clipinfo = ctx.load_json("video/clips.json", default={}) or {}
    if not steps:
        ctx.save_text("video/SKIPPED.txt", "no journey steps to storyboard")
        return
    dur = _durations(steps)
    canvas = clipinfo.get("canvas", {"width": 1920, "height": 1080, "scale": 2})

    clip_files = {c["screen"]: c.get("file", "") for c in clipinfo.get("clips", [])}
    clip_dur: dict[str, int] = {}
    for s in steps:
        c = s.get("clip", "")
        clip_dur[c] = max(clip_dur.get(c, 0), s.get("t_ms", 0) + _DEFAULT_TAIL_MS)

    shots = []
    for s in steps:
        shots.append({
            "index": s["index"], "kind": s.get("kind"), "action": s.get("action", ""),
            "screen": s.get("screen_url", ""), "clip": s.get("clip", ""),
            "clip_file": clip_files.get(s.get("clip", ""), ""),
            "t_ms": s.get("t_ms", 0), "duration_ms": dur.get(s["index"], _DEFAULT_TAIL_MS),
            "still_annotated": f'screenshots/{s.get("screenshot","")}' if s.get("screenshot") else "",
            "still_clean": f'screenshots/{s.get("result_screenshot","")}' if s.get("result_screenshot") else "",
            "highlight_rect": s.get("highlight_rect"),
            "caption": _caption(s), "network": s.get("network", []),
            "outputs": s.get("outputs", [])})

    shotlist = {
        "canvas": canvas,
        "clips": [{"screen": c["screen"], "file": c.get("file", ""),
                   "url": c.get("url", ""),
                   "duration_hint_ms": clip_dur.get(c["screen"], 0)}
                  for c in clipinfo.get("clips", [])],
        "cuts": clipinfo.get("cuts", []),
        "shots": shots,
        "notes": ("Clips are clean (no badges burned in); use highlight_rect to place "
                  "your own callouts. 'cuts' mark navigation-reset flicker spans to trim. "
                  "Stills are retina; record clips on a demo/seed account (footage is not "
                  "PII-redacted, stills are)."),
    }
    ctx.save_json("video/shotlist.json", shotlist)

    # ---------- storyboard.html ----------
    rows = []
    for sh in shots:
        a = (f'<img src="../{html.escape(sh["still_annotated"])}" loading="lazy">'
             if sh["still_annotated"] else '<div class="ph">no annotated frame</div>')
        c = (f'<img src="../{html.escape(sh["still_clean"])}" loading="lazy">'
             if sh["still_clean"] else '<div class="ph">— (no result frame)</div>')
        clip = (f'{html.escape(sh["clip"])} @ {_tc(sh["t_ms"])}'
                + (f' · {html.escape(sh["clip_file"].split("/")[-1])}' if sh["clip_file"] else ' · (no clip)'))
        net = html.escape(_net_line(sh))
        rows.append(
            f'<section><div class="hd"><span class="n">Shot {sh["index"]} · {html.escape(sh["kind"] or "")}'
            f'</span><span class="dur">{sh["duration_ms"]} ms</span></div>'
            f'<h3>{html.escape(sh["action"])}</h3>'
            f'<div class="pair"><figure><figcaption>annotated (for callout placement)</figcaption>{a}</figure>'
            f'<figure><figcaption>clean result</figcaption>{c}</figure></div>'
            f'<p>{html.escape(sh["caption"])}</p>'
            + (f'<code class="net">{net}</code>' if net else "")
            + f'<div class="meta">{clip} · <a href="{html.escape(sh["screen"])}">{html.escape(sh["screen"])}</a></div>'
            f'</section>')
    n_clips = len([c for c in shotlist["clips"] if c.get("file")])
    style = ("<style>body{font:15px system-ui;max-width:1080px;margin:24px auto;padding:0 16px;"
             "background:#0b0b0c;color:#eee}h1{font-size:22px}section{margin:0 0 36px;border-bottom:"
             "1px solid #222;padding-bottom:22px}.hd{display:flex;justify-content:space-between;"
             "align-items:center}.n{color:#ff3b6b;font-weight:600;font-size:12px}.dur{color:#888;"
             "font-size:12px}h3{margin:6px 0 12px}.pair{display:grid;grid-template-columns:1fr 1fr;"
             "gap:12px}figure{margin:0}figcaption{font-size:11px;color:#888;margin-bottom:4px}"
             "img{width:100%;border-radius:8px;border:1px solid #333}.ph{height:140px;display:flex;"
             "align-items:center;justify-content:center;color:#555;border:1px dashed #333;border-radius:8px}"
             ".net{display:block;margin-top:8px;color:#9ece6a;font-size:12px;white-space:pre-wrap}"
             ".meta{margin-top:8px;font-size:12px;color:#888}a{color:#7aa2f7;word-break:break-all}</style>")
    doc = (f"<!doctype html><meta charset=utf-8><title>Storyboard</title>{style}"
           f"<h1>Storyboard — {html.escape(cfg.target_url)}</h1>"
           f"<p style='color:#888'>{len(shots)} shots · {n_clips} clips · canvas "
           f"{canvas.get('width')}×{canvas.get('height')}@{canvas.get('scale')}× · "
           f"each shot below pairs the annotated frame (where to place a callout) with the "
           f"clean result frame. shotlist.json has the machine-readable version.</p>"
           f"{''.join(rows)}")
    ctx.save_text("video/storyboard.html", doc)
