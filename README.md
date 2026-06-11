# saascope

**Autonomous SaaS audit + walkthrough tooling.** Point it at a SaaS app. It logs
in, explores the **whole product** on its own — every screen, menu, tab, modal,
drawer and form — and screenshots **every step as a Scribe-style annotated
walkthrough** (numbered badge + box drawn on the exact element acted on, before
the shot). It captures **everything in and out of the SaaS**: the inputs it takes,
the outputs/exports it produces, and the **network I/O** (app API + third-party
calls) each action fires. Then an LLM of your choice writes the reports. The walk
itself uses **no LLM** — deterministic, exhaustive, reproducible. It produces an
**editor-ready video kit** (clean per-screen `.webm` clips + annotated/clean
stills + a storyboard + a shot list) for your video team to cut — but it does
**not** render a finished video itself: no stitched/edited mp4, no voiceover.

## What you get (per run, in `report/`)

- **`00_user_journey.md` / `.html`** — the centerpiece: a complete annotated
  walkthrough where **each step highlights the element acted on** (badge + box,
  optional spotlight + PII blur), captioned with what the user did. Inputs are
  documented as their own steps, and each step shows an **"under the hood"** line
  with the network it fired and any file it produced. Opens with an
  **Everything In & Out of the SaaS** summary (inputs · app API calls ·
  third-party services · outputs).
- **`01_audit_report.md`** — page/feature inventory, UI/UX, workflows, nav map,
  an **inputs/outputs & data-flow map**, detected integrations, issues.
- **`02_saas_overview.md`** — what it does, audience, value prop, features,
  pricing (if visible), positioning.
- **`03_demo_script.md`** — demo + onboarding video **scripts** (scene → VO →
  on-screen), mapped to the journey screenshots. Text only.
- **`04_bug_report.md`** — severity-tagged functional + visual bugs.

**Editor kit for the video team (in `video/`):**
- **`video/clips/<screen>.webm`** — one short **clean** screen-recording per screen
  (no badges burned in, so the team adds their own branded callouts).
- **`video/storyboard.html`** — visual storyboard: each step as **annotated still |
  clean result still**, with the action, the matching network/output line, the clip
  + timecode, and a suggested duration.
- **`video/shotlist.json`** — the machine-readable shot list the editor (or an
  automated pipeline) works straight from: ordered shots → annotated + clean frame
  paths, **highlight rect** (for precise callout placement), caption, clip name,
  **timecode**, suggested duration; plus per-clip info and **reset-flicker cut spans**
  to auto-trim.

Plus `screenshots/` (every shot + `manifest.jsonl` + `gallery.html`),
`crawl/inventory.json` + `tech_detected.json`, `explore/journey.json`,
**`explore/io_map.json`** (the aggregated in/out map), `explore/visited_urls.json`,
`qa/runtime_findings.json`.

## How it works

```
explore   exhaustive annotated walk (Playwright, no LLM)
          → breadth-first over every screen + every in-page action
            (menus, tabs, modals, drawers, forms)
          → 16:9 @2x retina; per step TWO stills: annotated pre-click + clean result
          → one short CLEAN .webm recorded per screen (with timecodes + cut spans)
          → inputs documented as steps; outputs (downloads) captured as steps
          → network listener tags each action's app-API + third-party calls
          → DOM-settle waits (no networkidle) + auto-dismiss cookie/consent popups
          → PII blur + destructive-action guard (never deletes/pays/saves/submits)
          → writes journey.json, io_map.json, visited_urls.json, runtime_findings.json
crawl     Crawl4AI → page inventory + tech/integration detection
journey   deterministic skeleton (+ optional LLM captions) → annotated walkthrough
qa        LLM → bug report (runtime signals + visual review)
analyze   LLM → audit report (incl. in/out + data-flow map)
overview  LLM → SaaS overview
script    LLM → demo/onboarding scripts
storyboard deterministic → video/ editor kit (shotlist.json + storyboard.html)
```

**For the video team:** clips are clean and per-screen (short, easy to scrub);
stills carry the badges; `shotlist.json` gives exact highlight rects + timecodes so
callouts land precisely; `cuts` mark the navigation-reset flicker to trim. Clips are
**not** PII-redacted (stills are) — **record on a demo/seed account.** No ffmpeg/TTS
in scope; a pristine render-from-stills mp4 is a deferred opt-in.

The journey agent enumerates the **real clickable elements** and lets the LLM pick
one by index (no coordinate-clicking, low hallucination). browser-use is available
as an optional engine (`exploration.engine: browser-use`) but the owned loop is the
default because it directly produces the ordered screenshot-per-step journey.

## Install & use

```bash
pip install -e . && playwright install chromium
saascope init                 # writes config.yaml + .env
saascope login                # opens a browser; log in by hand (SSO/2FA/CAPTCHA ok)
saascope run                  # full pipeline
saascope run --only journey   # re-narrate the walkthrough only (cheap iteration)
```

`saascope login` saves the session to `storage_state.json`; every run reuses it,
so you sidestep selector/SSO/2FA login entirely.

## Pick your LLM (config `llm` block)

| provider | model (writer) | explore_model | key |
|----------|----------------|---------------|-----|
| anthropic | claude-opus-4-8 | claude-sonnet-4-6 | `ANTHROPIC_API_KEY` |
| openai | gpt-5 | gpt-5-mini | `OPENAI_API_KEY` |
| gemini | gemini-2.5-pro | gemini-2.5-flash | `GOOGLE_API_KEY` |
| ollama | llama3.2-vision | llama3.2 | none (local) |

The cheap `explore_model` makes the per-click decisions; the strong `model` writes
the reports. Use a vision model for the visual bug review + journey captions.

## Safety

`safety.mode`:
- **read_only** (default) — navigate + read only; never submits/saves/mutates.
- **guarded** — blocks only clearly destructive actions (delete/pay/invite/logout).
- **off** — no guard; only for apps you own or throwaway accounts.

Always run against products you own or have permission to audit; autonomous use can
violate a SaaS's terms and trip anti-bot defenses.

## Swap matrix

| Slot | Default | Swap to | When |
|------|---------|---------|------|
| Brain | owned journey agent | browser-use | want its generality (accept API drift) |
| Brain | owned journey agent | Skyvern | vision-first for nasty/custom UIs |
| Sessions | local Chromium | Steel (self-host) / Browserbase | stealth, scale; replace `chromium.launch()` in `agent.py` with `connect_over_cdp()` |
| Writer | any LLM | — | set `llm.provider` |

## Cautions

- Credentials live only in `.env` (referenced as `env:VAR`); `.env`,
  `storage_state.json`, and `runs/` are gitignored.
- Cap `exploration.max_steps`; use a cheap/local `explore_model`.

## License
Choose your own (MIT recommended).
