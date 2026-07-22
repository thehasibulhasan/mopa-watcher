#!/usr/bin/env python3
"""
check_mopa.py

Checks two pages for new entries and sends a Telegram message for each new
item found:

  1) https://mopa.gov.bd/views/latest-news
     Plain server-rendered HTML -- scraped directly with requests+BeautifulSoup.

  2) https://www.gems.gov.bd/govt-order?organizationId=...&typeCode=POSTING&rankId=...
     A JavaScript single-page app -- the raw HTML is empty until JS runs, so
     this uses Playwright (headless Chromium) to render it first.

Designed to be run as a single pass (e.g. by GitHub Actions on a schedule)
rather than as a long-running loop.

Required environment variables (set as GitHub Actions secrets):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import os
import sys
import json
import time
import hashlib
from pathlib import Path

import requests
from bs4 import BeautifulSoup

MOPA_URL = "https://mopa.gov.bd/views/latest-news"
GEMS_URL = (
    "https://www.gems.gov.bd/govt-order"
    "?organizationId=77848f4b-3874-4cd5-b0a3-660660c046b3"
    "&typeCode=POSTING"
    "&rankId=c5c46e46-be48-49e9-9f56-6ac497a00e9f"
)

STATE_FILE = Path(__file__).parent / "seen_state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def log(msg: str) -> None:
    print(msg, flush=True)


def send_telegram_message(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, data=payload, timeout=20)
    if resp.status_code != 200:
        log(f"ERROR sending Telegram message [{resp.status_code}]: {resp.text}")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            data.setdefault("mopa", [])
            data.setdefault("gems", [])
            return data
        except Exception:
            log("WARNING: could not parse state file, starting fresh.")
    return {"mopa": [], "gems": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def item_id(url: str, title: str) -> str:
    return hashlib.sha256(f"{url}|{title}".encode("utf-8")).hexdigest()[:16]


def fetch_mopa_items() -> list[dict]:
    resp = requests.get(MOPA_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table")
    if not table:
        log("WARNING: no table found on MOPA page (layout may have changed).")
        return []

    items = []
    for row in table.find_all("tr"):
        link = row.find("a", href=True)
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link["href"]
        if href.startswith("/"):
            href = "https://mopa.gov.bd" + href
        cells = row.find_all("td")
        date_text = cells[-1].get_text(strip=True) if cells else ""
        if title:
            items.append({"title": title, "url": href, "date": date_text})
    return items


def fetch_gems_items() -> list[dict]:
    """
    gems.gov.bd is a JS-rendered SPA. We need a headless browser (Playwright)
    to execute the JS and then read the rendered DOM.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("ERROR: Playwright not installed -- skipping GEMS check this run.")
        return []

    items: list[dict] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(GEMS_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)

            try:
                page.wait_for_selector("table, .govt-order-list, [class*='order']", timeout=15000)
            except Exception:
                log("WARNING: GEMS expected content selector did not appear in time.")

            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        table = soup.find("table")
        if table:
            for row in table.find_all("tr"):
                link = row.find("a", href=True)
                text = row.get_text(" ", strip=True)
                if link:
                    href = link["href"]
                    if href.startswith("/"):
                        href = "https://www.gems.gov.bd" + href
                    title = link.get_text(strip=True) or text
                    if title:
                        items.append({"title": title, "url": href, "date": ""})
            if items:
                return items

        for link in soup.find_all("a", href=True):
            title = link.get_text(strip=True)
            href = link["href"]
            if not title or len(title) < 5:
                continue
            if href.startswith("/"):
                href = "https://www.gems.gov.bd" + href
            items.append({"title": title, "url": href, "date": ""})

    except Exception as e:
        log(f"ERROR fetching/rendering GEMS page: {e}")

    return items


def process_source(name: str, label: str, fetch_fn, state: dict) -> None:
    log(f"Checking {name} ...")
    try:
        items = fetch_fn()
    except Exception as e:
        log(f"ERROR fetching {name}: {e}")
        return

    if not items:
        log(f"{name}: no items retrieved this run.")
        return

    seen_ids = set(state.get(name, []))
    first_run = len(seen_ids) == 0

    if first_run:
        for it in items:
            seen_ids.add(item_id(it["url"], it["title"]))
        state[name] = list(seen_ids)[-500:]
        save_state(state)
        send_telegram_message(
            f"✅ {label} watcher is live. I'll message you whenever a new "
            f"entry appears (checked twice daily, 11 AM & 5 PM)."
        )
        log(f"{name}: baselined {len(items)} existing items. No alerts sent for these.")
        return

    new_items = []
    for it in items:
        iid = item_id(it["url"], it["title"])
        if iid not in seen_ids:
            new_items.append(it)
            seen_ids.add(iid)

    if new_items:
        log(f"{name}: {len(new_items)} new item(s) found.")
        for it in reversed(new_items):
            date_part = f"\n🗓 {it['date']}" if it.get("date") else ""
            msg = f"🔔 <b>{label}</b>\n\n{it['title']}{date_part}\n🔗 {it['url']}"
            send_telegram_message(msg)
            time.sleep(1)

        state[name] = list(seen_ids)[-500:]
        save_state(state)
    else:
        log(f"{name}: no new items this run.")


def main() -> int:
    state = load_state()

    process_source("mopa", "জনপ্রশাসন মন্ত্রণালয় — সর্বশেষ খবর (MOPA)", fetch_mopa_items, state)
    process_source("gems", "GEMS সরকারি আদেশ (Posting)", fetch_gems_items, state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
