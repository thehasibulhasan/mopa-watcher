#!/usr/bin/env python3
"""
check_mopa.py

Checks https://mopa.gov.bd/views/latest-news for new entries and sends a
Telegram message for each new one found. Designed to be run as a single pass
(e.g. by GitHub Actions on a schedule) rather than as a long-running loop.

Required environment variables (set as GitHub Actions secrets — see README):
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
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            log("WARNING: could not parse state file, starting fresh.")
    return {"seen": []}


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


def main() -> int:
    state = load_state()
    seen_ids = set(state.get("seen", []))
    first_run = len(seen_ids) == 0

    try:
        items = fetch_mopa_items()
    except Exception as e:
        log(f"ERROR fetching MOPA page: {e}")
        return 1

    if not items:
        log("No items retrieved this run (possible site issue).")
        return 0

    if first_run:
        # Baseline silently on the very first run so you don't get 30+ old
        # items dumped on you at once. Everything currently on the page is
        # marked as "already seen".
        for it in items:
            seen_ids.add(item_id(it["url"], it["title"]))
        state["seen"] = list(seen_ids)[-500:]
        save_state(state)
        send_telegram_message(
            "✅ MOPA latest-news watcher is live. I'll message you whenever "
            "a new entry appears (checked twice daily, 11 AM & 5 PM)."
        )
        log(f"Baselined {len(items)} existing items. No alerts sent for these.")
        return 0

    new_items = []
    for it in items:
        iid = item_id(it["url"], it["title"])
        if iid not in seen_ids:
            new_items.append(it)
            seen_ids.add(iid)

    if new_items:
        log(f"{len(new_items)} new item(s) found.")
        for it in reversed(new_items):  # oldest-first, chronological reading order
            date_part = f"\n🗓 {it['date']}" if it.get("date") else ""
            msg = f"🔔 <b>জনপ্রশাসন মন্ত্রণালয় — সর্বশেষ খবর</b>\n\n{it['title']}{date_part}\n🔗 {it['url']}"
            send_telegram_message(msg)
            time.sleep(1)

        state["seen"] = list(seen_ids)[-500:]
        save_state(state)
    else:
        log("No new items this run.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
