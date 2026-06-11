"""Exhaustive, annotated SaaS explorer — now producing an editor-ready kit.

Walks the WHOLE product breadth-first (every screen, menu, tab, modal, drawer,
form). For every interaction it captures TWO retina stills — an annotated
pre-click frame (Scribe-style numbered badge + box on the target) and a clean
settled-result frame — and records a short CLEAN screen-recording clip per
screen. Inputs are documented as steps; outputs (downloads) and network I/O
(app API + third-party calls) are captured per step. A storyboard stage turns
all of this into shotlist.json + storyboard.html for the video team.

Deterministic: no LLM in the walk. Reliability: no networkidle; DOM-settle waits
+ interstitial dismissal. Safety: read_only guard + PII redaction bars on stills.
"""
from __future__ import annotations
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin

from .config import Config
from .context import RunContext

# ---- injected browser scripts ---------------------------------------------

_JS_CLICKABLES = r"""
() => {
  const sel='a[href],button,[role=button],[role=menuitem],[role=tab],[role=link],summary,[onclick]';
  const out=[]; let i=0;
  for(const el of document.querySelectorAll(sel)){
    const r=el.getBoundingClientRect(); const cs=getComputedStyle(el);
    if(r.width<=0||r.height<=0||cs.visibility==='hidden'||cs.display==='none') continue;
    el.setAttribute('data-sc-idx', String(i));
    const text=(el.innerText||el.getAttribute('aria-label')||el.getAttribute('title')||'').trim().replace(/\s+/g,' ').slice(0,80);
    out.push({idx:i, text, role:el.getAttribute('role')||el.tagName.toLowerCase(),
              href:el.getAttribute('href')||'', tag:el.tagName.toLowerCase()});
    if(++i>150) break;
  }
  return out;
}
"""

_JS_INPUTS = r"""
() => {
  const sel='input:not([type=hidden]):not([type=submit]):not([type=button]),textarea,select,[role=textbox],[role=combobox],[contenteditable=true]';
  const out=[]; let i=0;
  for(const el of document.querySelectorAll(sel)){
    const r=el.getBoundingClientRect(); const cs=getComputedStyle(el);
    if(r.width<=0||r.height<=0||cs.visibility==='hidden'||cs.display==='none') continue;
    el.setAttribute('data-sc-in', String(i));
    let label='';
    if(el.labels&&el.labels[0]) label=el.labels[0].innerText;
    label=(label||el.getAttribute('aria-label')||el.getAttribute('placeholder')||el.name||'').trim().slice(0,60);
    out.push({idx:i, label:label||(el.type||el.tagName.toLowerCase()),
              type:(el.type||el.tagName.toLowerCase())});
    if(++i>60) break;
  }
  return out;
}
"""

# draw badge+box for each {idx,n}; optional spotlight dim; returns first rect
_JS_ANNOTATE = r"""
(args) => {
  const {attr, items, spotlight} = args;
  let first=null;
  items.forEach(it=>{
    const el=document.querySelector(`[${attr}="${it.idx}"]`);
    if(!el) return;
    el.scrollIntoView({block:'center', inline:'center'});
    const r=el.getBoundingClientRect(); const pad=4;
    if(!first) first={x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)};
    const box=document.createElement('div'); box.className='__sc_anno';
    box.style.cssText=`position:fixed;left:${r.left-pad}px;top:${r.top-pad}px;width:${r.width+2*pad}px;height:${r.height+2*pad}px;border:3px solid #ff3b6b;border-radius:6px;z-index:2147483646;pointer-events:none;`+(spotlight?`box-shadow:0 0 0 9999px rgba(0,0,0,.45);`:``);
    const badge=document.createElement('div'); badge.className='__sc_anno';
    badge.textContent=it.n;
    badge.style.cssText=`position:fixed;left:${r.left-pad-10}px;top:${r.top-pad-12}px;min-width:22px;height:22px;line-height:22px;text-align:center;background:#ff3b6b;color:#fff;font:700 12px system-ui;border-radius:11px;padding:0 6px;z-index:2147483647;pointer-events:none;`;
    document.body.appendChild(box); document.body.appendChild(badge);
  });
  return first;
}
"""

# surgical PII redaction: solid bars over matched rects (no DOM mutation)
_JS_REDACT = r"""
() => {
  const add=(r)=>{ if(!r||r.width<=0||r.height<=0) return;
    const d=document.createElement('div'); d.className='__sc_anno';
    d.style.cssText=`position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;background:#1b1b1f;border-radius:3px;z-index:2147483645;pointer-events:none;`;
    document.body.appendChild(d); };
  const rx=/([a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})|(\+?\d[\d ()\-]{7,}\d)/ig;
  const w=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let c=0;
  while(w.nextNode() && c<600){ const n=w.currentNode; const pe=n.parentElement;
    if(!pe || /SCRIPT|STYLE|NOSCRIPT/.test(pe.tagName)) continue;
    const t=n.nodeValue||''; rx.lastIndex=0; let m;
    while((m=rx.exec(t))){ try{ const rg=document.createRange();
      rg.setStart(n,m.index); rg.setEnd(n,m.index+m[0].length);
      for(const r of rg.getClientRects()) add(r); c++; }catch(e){} } }
  document.querySelectorAll('input,textarea').forEach(el=>{
    if(el.type==='password'||(el.value&&el.value.length>0)) add(el.getBoundingClientRect()); });
}
"""

_JS_CLEAR = "() => document.querySelectorAll('.__sc_anno').forEach(e=>e.remove())"

_DISMISS_TEXT = ["accept all", "accept", "agree", "got it", "ok", "okay",
                 "dismiss", "close", "no thanks", "skip", "continue", "i agree"]

_DESTRUCTIVE_TEXT = [r"delet", r"remov", r"deactivat", r"\bcancel", r"unsubscrib",
                     r"\bpay\b", r"purchas", r"\bbuy\b", r"checkout", r"invit",
                     r"log\s?out", r"sign\s?out", r"destroy", r"\breset", r"revok",
                     r"terminat", r"close account", r"downgrade", r"\bsave\b",
                     r"\bsubmit\b", r"\bapply\b", r"\bconfirm\b", r"\bsend\b",
                     r"\bpublish\b", r"\bdelete\b"]
_DESTRUCTIVE_URL = [r"/billing", r"/payment", r"/delete", r"/danger",
                    r"/logout", r"/signout"]


def _allowed(el: dict, off: bool) -> bool:
    if off:
        return True
    t = (el.get("text") or "").lower()
    h = (el.get("href") or "").lower()
    if any(re.search(p, t) for p in _DESTRUCTIVE_TEXT):
        return False
    if any(re.search(p, h) for p in _DESTRUCTIVE_URL):
        return False
    return True


def _norm_label(s: str) -> str:
    return re.sub(r"\d+", "#", (s or "").lower()).strip()


def _norm_path(u: str) -> str:
    p = urlparse(u).path
    return re.sub(r"/\d+", "/:id", p) or "/"


def _reg_domain(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _slug(url: str) -> str:
    p = urlparse(url).path.strip("/") or "home"
    return re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-")[:48] or "home"


async def _settle(page, timeout_ms: int = 6000) -> None:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass
    try:
        await page.wait_for_function(
            """() => { window.__scLast = window.__scLast||{h:0,t:0};
                const h=document.body?document.body.innerHTML.length:0;
                const now=Date.now();
                if(h!==window.__scLast.h){window.__scLast={h,t:now}; return false;}
                return now-window.__scLast.t>400; }""",
            timeout=timeout_ms)
    except Exception:
        pass


async def _dismiss_interstitials(page) -> None:
    for label in _DISMISS_TEXT:
        try:
            btn = page.get_by_role("button", name=re.compile(rf"^\s*{label}\s*$", re.I))
            if await btn.count():
                await btn.first.click(timeout=1500)
                await _settle(page, 2500)
                return
        except Exception:
            continue


class Explorer:
    def __init__(self, cfg: Config, ctx: RunContext):
        self.cfg, self.ctx = cfg, ctx
        self.guard_off = cfg.get("safety", "mode", default="read_only") == "off"
        self.spotlight = bool(cfg.get("annotate", "spotlight", default=True))
        self.redact = bool(cfg.get("annotate", "redact", default=True))
        self.record = bool(cfg.get("video", "record", default=True))
        self.max_steps = int(cfg.get("exploration", "max_steps", default=120))
        self.max_per_screen = int(cfg.get("exploration", "max_actions_per_screen", default=25))
        self.headless = bool(cfg.get("exploration", "headless", default=True))
        self.scale = int(cfg.get("video", "device_scale_factor", default=2))
        self.viewport = cfg.get("video", "canvas",
                                default={"width": 1920, "height": 1080})
        self.origin = _reg_domain(urlparse(cfg.target_url).netloc)
        self.video_dir = ctx.dir / "video"
        self.clips_dir = self.video_dir / "clips"
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.journey: list[dict] = []
        self.clips: list[dict] = []
        self.cuts: list[dict] = []
        self.responses: list[dict] = []
        self.downloads: list[dict] = []
        self.console_errors, self.page_errors = [], []
        self.io_inputs: list[dict] = []
        self.visited_urls: list[str] = []
        self._acted: set[str] = set()   # (screen, normalized-label) — per-screen dedup
        self._t0 = 0.0

    def _ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    # ---- capture: render bytes + rect, NEVER persist here (caller decides) ----
    async def _render(self, page, *, attr: str, items: list[dict]):
        rect = None
        try:
            if self.redact:
                try: await page.evaluate(_JS_REDACT)
                except Exception: pass
            if items:
                try:
                    rect = await page.evaluate(_JS_ANNOTATE,
                        {"attr": attr, "items": items, "spotlight": self.spotlight})
                except Exception:
                    rect = None
                # let scroll/layout settle so the box lands on the element
                try: await page.wait_for_timeout(120)
                except Exception: pass
            try:
                data = await page.screenshot(full_page=False)
            except Exception:
                data = None          # bad capture → skip this step, keep walking
            return data, rect
        finally:
            try: await page.evaluate(_JS_CLEAR)
            except Exception: pass

    def _persist(self, data: bytes, page, label: str, kind: str, meta: dict) -> str:
        rec = self.ctx.store.add_bytes(data, stage="journey", url=getattr(page, "url", ""),
                                       title=label, label=kind, meta=meta)
        return rec["file"]

    def _classify(self, r: dict) -> dict:
        host = urlparse(r["url"]).netloc
        origin = "app" if _reg_domain(host) == self.origin else "third_party"
        return {"method": r["method"], "path": _norm_path(r["url"]),
                "host": host, "status": r["status"], "kind": r["kind"],
                "origin": origin, "url": r["url"]}

    def _step_network(self, start: int) -> list[dict]:
        out, seen = [], set()
        for r in self.responses[start:]:
            if r["kind"] not in ("xhr", "fetch", "document"):
                continue
            c = self._classify(r)
            key = (c["method"], c["path"], c["origin"])
            if key in seen:
                continue
            seen.add(key); out.append(c)
        return out

    def _attach(self, page) -> None:
        page.on("response", lambda r: self.responses.append(
            {"url": r.url, "status": r.status, "method": r.request.method,
             "kind": r.request.resource_type}))
        page.on("download", lambda d: self.downloads.append(
            {"name": d.suggested_filename, "url": d.url}))
        page.on("console", lambda m: self.console_errors.append(
            {"text": m.text}) if m.type == "error" else None)
        page.on("pageerror", lambda e: self.page_errors.append({"error": str(e)}))

    async def run(self) -> None:
        from playwright.async_api import async_playwright
        session_file = Path(self.cfg.get("auth", "session_file", default="storage_state.json"))

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            try:
                if not session_file.exists():
                    await self._bootstrap_login(browser, session_file)

                url_frontier = [self.cfg.target_url]
                visited: set[str] = set()
                while url_frontier and len(self.journey) < self.max_steps:
                    url = url_frontier.pop(0)
                    key = _norm_path(url)
                    if key in visited:
                        continue
                    visited.add(key)
                    await self._explore_screen(browser, url, session_file, url_frontier)
            finally:
                self._finalize()   # ALWAYS writes, even on mid-walk failure
                try: await browser.close()
                except Exception: pass

    async def _new_context(self, browser, session_file: Path, record: bool):
        kw = {"viewport": self.viewport, "device_scale_factor": self.scale,
              "accept_downloads": True}
        if session_file.exists():
            kw["storage_state"] = str(session_file)
        if record and self.record:
            kw["record_video_dir"] = str(self.clips_dir)
            kw["record_video_size"] = self.viewport
        return await browser.new_context(**kw)

    async def _bootstrap_login(self, browser, session_file: Path) -> None:
        a = self.cfg.get("auth", default={}) or {}
        if not (a.get("username_selector") and a.get("password_selector")):
            return
        ctx = await self._new_context(browser, session_file, record=False)
        page = await ctx.new_page()
        try:
            await page.goto(self.cfg.login_url, wait_until="domcontentloaded")
            await page.fill(a["username_selector"], a["username"])
            await page.fill(a["password_selector"], a["password"])
            if a.get("submit_selector"):
                await page.click(a["submit_selector"])
            else:
                await page.keyboard.press("Enter")
            await _settle(page)
            session_file.write_text(__import__("json").dumps(await ctx.storage_state()))
        except Exception:
            pass
        finally:
            try: await ctx.close()
            except Exception: pass

    async def _explore_screen(self, browser, url: str, session_file: Path,
                              url_frontier: list) -> None:
        ctx = await self._new_context(browser, session_file, record=True)
        page = await ctx.new_page()
        self._attach(page)
        slug = _slug(url)
        clip_steps: list[int] = []
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _settle(page)
            await _dismiss_interstitials(page)
            self._t0 = time.monotonic()
            if page.url not in self.visited_urls:
                self.visited_urls.append(page.url)
            title = await page.title()

            # 1) landing — clean still
            await self._step_landing(page, title, slug, clip_steps)
            # 2) inputs — annotated still documenting what goes IN
            await self._step_inputs(page, title, slug, clip_steps)
            # 3) every in-page action — annotated pre + clean result
            await self._exercise(page, url, slug, clip_steps, url_frontier)
        except Exception:
            pass
        finally:
            video = page.video
            try: await ctx.close()
            except Exception: pass
            clip_file = ""
            if video:
                try:
                    src = Path(await video.path())
                    dst = self.clips_dir / f"{slug}.webm"
                    if src.exists():
                        src.replace(dst); clip_file = f"video/clips/{dst.name}"
                except Exception:
                    pass
            if clip_steps:
                self.clips.append({"screen": slug, "url": url, "file": clip_file,
                                   "steps": clip_steps})

    async def _step_landing(self, page, title, slug, clip_steps):
        if len(self.journey) >= self.max_steps:
            return
        idx = len(self.journey)
        data, _ = await self._render(page, attr="data-sc-idx", items=[])
        if data is None:
            return
        shot = self._persist(data, page, title, "screen", {"kind": "screen"})
        self.journey.append({"index": idx, "kind": "screen", "screen_url": page.url,
                             "title": title, "action": f"Open screen: {title}",
                             "target": "", "screenshot": shot, "result_screenshot": "",
                             "highlight_rect": None, "annotated": False,
                             "clip": slug, "t_ms": self._ms(),
                             "network": [], "outputs": []})
        clip_steps.append(idx)

    async def _step_inputs(self, page, title, slug, clip_steps):
        if len(self.journey) >= self.max_steps:
            return
        try:
            inputs = await page.evaluate(_JS_INPUTS)
        except Exception:
            inputs = []
        if not inputs:
            return
        items = [{"idx": i["idx"], "n": k + 1} for k, i in enumerate(inputs[:12])]
        idx = len(self.journey)
        data, rect = await self._render(page, attr="data-sc-in", items=items)
        if data is None:
            return
        shot = self._persist(data, page, f"{title} — inputs", "input_map",
                             {"kind": "input_map"})
        for i in inputs:
            self.io_inputs.append({"label": i["label"], "type": i["type"], "screen": page.url})
        self.journey.append({"index": idx, "kind": "input_map", "screen_url": page.url,
                             "title": title, "action": "Inputs on this screen (data goes in here)",
                             "target": "", "screenshot": shot, "result_screenshot": "",
                             "highlight_rect": rect, "annotated": bool(items),
                             "clip": slug, "t_ms": self._ms(),
                             "inputs": [{"label": i["label"], "type": i["type"]} for i in inputs],
                             "network": [], "outputs": []})
        clip_steps.append(idx)

    async def _exercise(self, page, base_url, slug, clip_steps, url_frontier):
        try:
            clickables = await page.evaluate(_JS_CLICKABLES)
        except Exception:
            return
        acted_here = 0
        for el in clickables:
            if len(self.journey) >= self.max_steps or acted_here >= self.max_per_screen:
                break
            if not _allowed(el, self.guard_off):
                continue
            if el["href"]:
                try: full = urljoin(page.url, el["href"])
                except Exception: full = el["href"]
                if full.startswith("http") and _reg_domain(urlparse(full).netloc) == self.origin:
                    if _norm_path(full) not in {_norm_path(u) for u in url_frontier}:
                        url_frontier.append(full)
                    continue
            nlab = _norm_label(el["text"])
            dedup_key = f"{slug}::{nlab}"
            if not nlab or dedup_key in self._acted:
                continue
            self._acted.add(dedup_key)
            idx = len(self.journey)

            # annotated pre-click still (held in memory until the click succeeds)
            pre, rect = await self._render(page, attr="data-sc-idx",
                                           items=[{"idx": el["idx"], "n": idx}])
            if pre is None:
                continue
            t_ms = self._ms()
            net_start, dl_start = len(self.responses), len(self.downloads)
            try:
                await page.click(f'[data-sc-idx="{el["idx"]}"]', timeout=6000)
                await _settle(page)
            except Exception:
                continue   # click failed → discard the pre frame, NO orphan persisted
            acted_here += 1
            # clean settled-result still
            post, _ = await self._render(page, attr="data-sc-idx", items=[])
            pre_file = self._persist(pre, page, el["text"], "action",
                                     {"kind": "action", "rect": rect, "annotated": bool(rect)})
            post_file = self._persist(post, page, f"{el['text']} — result", "result",
                                      {"kind": "result"}) if post is not None else ""
            self.journey.append({
                "index": idx, "kind": "action", "screen_url": base_url,
                "title": el["text"], "action": f"Click '{el['text']}'",
                "target": el["text"], "screenshot": pre_file,
                "result_screenshot": post_file, "highlight_rect": rect,
                "annotated": bool(rect), "clip": slug, "t_ms": t_ms,
                "network": self._step_network(net_start),
                "outputs": [{"type": "download", **d} for d in self.downloads[dl_start:]]})
            clip_steps.append(idx)
            # reset SPA state for the next element — mark the flicker as a cut
            cut_a = self._ms()
            try:
                await page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
                await _settle(page)
                await page.evaluate(_JS_CLICKABLES)
                self.cuts.append({"clip": slug, "start_ms": cut_a, "end_ms": self._ms(),
                                  "reason": "navigation-reset"})
            except Exception:
                break

    def _finalize(self) -> None:
        app_ep, third, outs = {}, {}, []
        for s in self.journey:
            for c in s.get("network", []):
                if c["origin"] == "app" and c["kind"] in ("xhr", "fetch"):
                    k = f'{c["method"]} {c["path"]}'
                    app_ep[k] = app_ep.get(k, 0) + 1
                elif c["origin"] == "third_party":
                    third[c["host"]] = third.get(c["host"], 0) + 1
            for o in s.get("outputs", []):
                outs.append(o)
        io_map = {"inputs": _dedupe(self.io_inputs, ("label", "type")),
                  "app_endpoints": [{"endpoint": k, "count": v} for k, v in sorted(app_ep.items())],
                  "third_party_services": [{"host": k, "count": v} for k, v in sorted(third.items())],
                  "outputs": outs}
        self.ctx.save_json("explore/journey.json", self.journey)
        self.ctx.save_json("explore/io_map.json", io_map)
        self.ctx.save_json("explore/visited_urls.json", self.visited_urls)
        self.ctx.save_json("video/clips.json", {"clips": self.clips, "cuts": self.cuts,
                                                "canvas": {**self.viewport, "scale": self.scale}})
        self.ctx.save_json("qa/runtime_findings.json", {
            "console_errors": self.console_errors, "page_errors": self.page_errors,
            "failed_requests": [self._classify(r) for r in self.responses if r["status"] >= 400][:200],
            "broken_links": [], "accessibility": []})


def _dedupe(rows: list[dict], keys) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = tuple(r.get(x) for x in keys)
        if k in seen:
            continue
        seen.add(k); out.append(r)
    return out


async def run(cfg: Config, ctx: RunContext, client=None) -> None:
    try:
        import playwright  # noqa
    except Exception as e:  # pragma: no cover
        ctx.save_text("explore/SKIPPED.txt", f"playwright not importable: {e}")
        return
    await Explorer(cfg, ctx).run()
