"""saascope CLI."""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path

from .config import Config
from . import pipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="saascope", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="write starter config.yaml + .env")
    p_init.add_argument("--force", action="store_true")

    p_login = sub.add_parser("login", help="open a browser, log in by hand, save the session")
    p_login.add_argument("--config", default="config.yaml")

    p_run = sub.add_parser("run", help="run the audit pipeline")
    p_run.add_argument("--config", default="config.yaml")
    p_run.add_argument("--only",
                       help="comma list: explore,crawl,qa,journey,analyze,overview,script")

    args = parser.parse_args()
    if args.cmd == "init":
        _init(args.force)
    elif args.cmd == "login":
        _login(Config.load(args.config))
    elif args.cmd == "run":
        only = set(args.only.split(",")) if args.only else None
        pipeline.run(Config.load(args.config), only=only)


def _init(force: bool) -> None:
    pkg = Path(__file__).resolve().parent.parent
    for src, dst in [("config.example.yaml", "config.yaml"), (".env.example", ".env")]:
        target = Path(dst)
        if target.exists() and not force:
            print(f"skip {dst} (exists; use --force)")
            continue
        shutil.copy(pkg / src, target)
        print(f"wrote {dst}")
    print("Edit config.yaml + .env, then: saascope login  (once), then: saascope run")


def _login(cfg: Config) -> None:
    """Headed browser; you log in manually (SSO/2FA/CAPTCHA all fine); save state."""
    from playwright.sync_api import sync_playwright
    session_file = Path(cfg.get("auth", "session_file", default="storage_state.json"))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(cfg.login_url)
        input("A browser opened. Log in fully, then press Enter here to save the session... ")
        session_file.write_text(__import__("json").dumps(context.storage_state()))
        browser.close()
    print(f"Saved session to {session_file}. Runs will reuse it.")


if __name__ == "__main__":
    main()
