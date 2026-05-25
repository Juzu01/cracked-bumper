"""
cracked.st thread bumper (manual-cookie edition)
------------------------------------------------
Reads cookies from cookies.txt that you paste from DevTools.
Zero automation on login = zero detection.

HOW TO PREPARE cookies.txt:
  1. Open cracked.st in your normal Chrome and log in.
  2. F12 -> Console tab, paste:   copy(document.cookie)
  3. Paste into cookies.txt next to this script and save.

USAGE:
    py bumper.py --dry-run
    py bumper.py
    py bumper.py --delay 15
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://cracked.st"

# ===== CONFIGURE THIS =====
# Go to cracked.st, search for your threads, copy the search results URL.
# It looks like: https://cracked.st/search.php?action=results&sid=XXXXXXXX
DEFAULT_SEARCH_URL = "YOUR_SEARCH_URL_HERE"
# ===========================

COOKIES_FILE = Path(__file__).parent / "cookies.txt"
LOG_FILE = Path(__file__).parent / "bumper.log"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)

TID_RE = re.compile(r"tid=(\d+)", re.IGNORECASE)


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def notify(title: str, message: str) -> None:
    """Windows toast notification (silent fallback if it fails)."""
    t = title.replace("'", "''")
    m = message.replace("'", "''")
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, "
        "Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, "
        "Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\">"
        f"<text>{t}</text><text>{m}</text></binding></visual></toast>');"
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
        "[Windows.UI.Notifications.ToastNotificationManager]"
        "::CreateToastNotifier('CrackedBumper').Show($toast);"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            timeout=10, capture_output=True,
        )
    except Exception:
        pass


def parse_cookies_file(path: Path) -> dict[str, str]:
    """
    Accepts 3 formats:
      A) "name=value; name2=value2" (from document.cookie)
      B) Netscape cookies.txt (tab-separated lines)
      C) DevTools Application tab (copied table)
    """
    if not path.exists():
        raise SystemExit(
            f"!! Missing {path.name}.\n"
            "Create cookies.txt next to bumper.py.\n"
            "Easiest: on cracked.st press F12, Console tab, paste:\n"
            "   copy(document.cookie)\n"
            "then Ctrl+V into cookies.txt and save."
        )
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise SystemExit("!! cookies.txt is empty.")

    cookies: dict[str, str] = {}

    # Format A: single-line "k=v; k2=v2"
    if ";" in raw and "\n" not in raw.strip():
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies

    # Format B/C: multi-line
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
                continue
            if len(parts) >= 2:
                cookies[parts[0]] = parts[1]
                continue
        m = re.match(r"(\S+)\s+(\S+)", line)
        if m:
            name, val = m.group(1), m.group(2)
            if name.lower() in {"name", "cookie"}:
                continue
            cookies[name] = val
            continue
        if "=" in line:
            for part in line.split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()

    if not cookies:
        raise SystemExit("!! Could not parse cookies.txt.")
    return cookies


def make_session(cookies: dict[str, str], ua: str) -> requests.Session:
    s = requests.Session()
    for k, v in cookies.items():
        s.cookies.set(k, v, domain=".cracked.st")
    s.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Referer": BASE + "/",
        "Sec-Ch-Ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    })
    return s


def check_logged_in(s: requests.Session) -> str | None:
    r = s.get(BASE + "/", timeout=20)
    if r.status_code != 200:
        log(f"GET / returned {r.status_code}")
        if r.status_code == 403:
            log("   -> 403 usually = Cloudflare blocking you. Check cf_clearance cookie.")
        return None
    text = r.text
    m = re.search(r"Welcome back,?\s*<[^>]+>([^<]+)<", text)
    if m:
        return m.group(1).strip()
    if "member.php?action=login" in text.lower():
        return None
    return "(logged in)"


def _extract_from_soup(soup: BeautifulSoup, seen: set[str],
                       results: list[tuple[str, str]]) -> int:
    added = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "action=bump_thread" not in href.lower():
            continue
        m = TID_RE.search(href)
        if not m:
            continue
        tid = m.group(1)
        if tid in seen:
            continue
        seen.add(tid)
        full = urljoin(BASE + "/", href.lstrip("/"))
        results.append((tid, full))
        added += 1
    return added


def _count_thread_rows(soup: BeautifulSoup) -> int:
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "showthread.php" not in href.lower():
            continue
        m = TID_RE.search(href)
        if m:
            seen.add(m.group(1))
    return len(seen)


def collect_bump_links(s: requests.Session, search_url: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    total_rows = 0
    page = 1
    while True:
        sep = "&" if "?" in search_url else "?"
        url = search_url if page == 1 else f"{search_url}{sep}page={page}"
        log(f"Fetching page {page}: {url}")
        r = s.get(url, timeout=30)
        if r.status_code != 200:
            log(f"!! page {page} returned {r.status_code}, stopping pagination")
            break
        soup = BeautifulSoup(r.text, "html.parser")
        added = _extract_from_soup(soup, seen, results)
        rows = _count_thread_rows(soup)
        total_rows += rows
        log(f"  page {page}: {rows} threads visible, {added} with Bump button")

        next_page = page + 1
        has_next = False
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if f"page={next_page}" in h:
                has_next = True
                break
            cls = a.get("class") or []
            if "pagination_next" in cls and "page=" in h:
                has_next = True
                break
        if not has_next:
            log(f"  no link to page {next_page}, done.")
            break
        if rows == 0:
            log("  zero threads on page, stopping.")
            break
        page += 1
        if page > 50:
            log("  safety stop: over 50 pages.")
            break
        time.sleep(1.0)

    log(f"Total threads in results: {total_rows}")
    return results


def bump_one(s: requests.Session, url: str) -> str:
    try:
        r = s.get(url, timeout=20)
    except requests.RequestException as e:
        return f"err:{e.__class__.__name__}"
    body = r.text.lower()
    if r.status_code == 403:
        return "403"
    if "bumped" in body:
        return "ok"
    if "wait" in body and ("second" in body or "minute" in body or "hour" in body):
        return "cooldown"
    if "no permission" in body or "not have permission" in body:
        return "no_perm"
    if "invalid post key" in body or "mismatched post key" in body:
        return "bad_key"
    if r.status_code != 200:
        return f"http{r.status_code}"
    return "ok?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=12.0)
    ap.add_argument("--search-url", default=DEFAULT_SEARCH_URL)
    ap.add_argument("--cookies", default=str(COOKIES_FILE))
    ap.add_argument("--ua", default=DEFAULT_UA)
    args = ap.parse_args()

    if args.search_url == "YOUR_SEARCH_URL_HERE":
        raise SystemExit(
            "!! You need to set your search URL first.\n"
            "Open bumper.py and replace YOUR_SEARCH_URL_HERE with your\n"
            "cracked.st search results URL.\n"
            "Or pass it as: py bumper.py --search-url \"https://cracked.st/search.php?...\""
        )

    log("=" * 60)
    log("cracked.st bumper start")

    cookies = parse_cookies_file(Path(args.cookies))
    log(f"Loaded {len(cookies)} cookies: {', '.join(sorted(cookies))}")
    s = make_session(cookies, args.ua)

    user = check_logged_in(s)
    if not user:
        log("!! NOT logged in. Cookies expired or incomplete.")
        log("   Copy cookies again from DevTools (F12 -> Console -> copy(document.cookie)).")
        return 1
    log(f"Logged in as: {user}")

    threads = collect_bump_links(s, args.search_url)
    log(f"Found {len(threads)} threads with Bump button.")
    for tid, _ in threads:
        log(f"  tid={tid}")

    if args.dry_run:
        log("--dry-run, stopping.")
        return 0
    if not threads:
        log("No threads to bump — all on cooldown.")
        notify("CrackedBumper", "No threads to bump — all on cooldown.")
        return 0

    ok = cooldown = bad = 0
    for i, (tid, url) in enumerate(threads, 1):
        log(f"[{i}/{len(threads)}] bumping tid={tid}")
        status = bump_one(s, url)
        log(f"  -> {status}")
        if status.startswith("ok"):
            ok += 1
        elif status == "cooldown":
            cooldown += 1
        else:
            bad += 1
        if i < len(threads):
            time.sleep(args.delay)

    log("=" * 60)
    log(f"DONE. ok={ok} cooldown={cooldown} other={bad}")
    notify("CrackedBumper - done", f"Bumped: {ok} | Cooldown: {cooldown} | Other: {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
