import json
import smtplib
import sys
import unicodedata
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

CONFIG_FILE = Path(__file__).parent / "config.json"
STATE_FILE = Path(__file__).parent / "state.json"
LOG_FILE = Path(__file__).parent / "monitor.log"



def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(path: Path, default=None):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def fetch_copy(url: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",  # use real installed Chrome, not bundled Chromium
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-GB",
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page.goto(url, wait_until="load", timeout=30000)
        page.wait_for_timeout(2500)  # let JS finish rendering content

        title = page.title().strip()

        # Intro copy — try known XPaths using Playwright's native locator API
        INTRO_XPATHS = [
            "//*[@id='app-main']/div/div/div/div[1]/div[1]/div",
            "//*[@id='app-main']/div/div[2]/div[1]/div",
            "//*[@id='app-main']/div/div[2]/div/div/div[1]/div",
        ]

        def is_prose(text):
            return len(text) > 40 and any(c in text for c in '.!?')

        intro = ""
        for xpath in INTRO_XPATHS:
            try:
                container = page.locator(f'xpath={xpath}').first
                # Try <p> tags within the container first
                for p_el in container.locator('p').all():
                    try:
                        text = p_el.inner_text(timeout=1000).strip()
                        if is_prose(text):
                            intro = text
                            break
                    except Exception:
                        continue
                if intro:
                    break
                # Fallback: get full container text, strip heading lines, take first prose line
                full = container.inner_text(timeout=2000).strip()
                headings = container.locator('h1, h2, h3, h4').all()
                for h in headings:
                    try:
                        full = full.replace(h.inner_text(timeout=500).strip(), '').strip()
                    except Exception:
                        pass
                for line in full.splitlines():
                    line = line.strip()
                    if is_prose(line):
                        intro = line
                        break
                if intro:
                    break
            except Exception:
                continue

        # H1 — iterate all h1s, skip any whose visible text is just the brand logo word
        h1 = ""
        for h1_el in page.locator("h1").all():
            try:
                text = h1_el.inner_text(timeout=1000).strip()
                if text and text.lower() != "pandora":
                    h1 = text
                    break
            except Exception:
                continue

        html = page.content()
        browser.close()

    # Meta description from rendered HTML
    soup = BeautifulSoup(html, "html.parser")
    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag.get("content", "").strip() if desc_tag else ""

    return {"title": title, "meta_description": description, "intro_copy": intro, "h1": h1}


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().lower()


def fields_match(live: dict, saved: dict) -> tuple[bool, list[str]]:
    """Return (all_match, list_of_mismatches)."""
    active_fields = [
        key for key in ("title", "meta_description", "intro_copy", "h1")
        if saved.get(key, "").strip() and not saved[key].strip().startswith("PASTE THE EXACT")
    ]
    if not active_fields:
        return False, ["no saved copy configured yet"]
    mismatches = [
        key for key in active_fields
        if _normalise(live.get(key, "")) != _normalise(saved[key])
    ]
    return len(mismatches) == 0, mismatches


def send_email(cfg: dict, subject: str, html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["gmail_sender"]
    msg["To"] = cfg["notify_email"]
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(cfg["gmail_sender"], cfg["gmail_app_password"])
        server.sendmail(cfg["gmail_sender"], cfg["notify_email"], msg.as_string())


def build_email_body(url: str, live: dict, saved: dict, all_match: bool) -> str:
    now = datetime.now().strftime("%d %b %Y, %H:%M")

    def row(label, live_val, saved_val):
        matches = live_val.strip().lower() == saved_val.strip().lower()
        if matches:
            bg, fg = "#edfaf1", "#1a7a3e"
        else:
            bg, fg = "#fdecea", "#b71c1c"
        cell = f'style="padding:10px 12px;background:{bg};color:{fg};vertical-align:top"'
        return f"""
        <tr>
          <td style="padding:10px 12px;font-weight:600;color:#555;white-space:nowrap;vertical-align:top">{label}</td>
          <td style="padding:10px 12px;color:#222;vertical-align:top">{live_val}</td>
          <td {cell}>{saved_val}</td>
        </tr>"""

    rows = row("Title", live["title"], saved.get("title", ""))
    rows += row("Meta description", live["meta_description"], saved.get("meta_description", ""))
    rows += row("Intro copy", live.get("intro_copy", ""), saved.get("intro_copy", ""))
    rows += row("H1", live.get("h1", ""), saved.get("h1", ""))

    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)">

        <tr>
          <td style="background:#1a1a1a;padding:28px 32px">
            <p style="margin:0;font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:1px">Site Monitor</p>
            <h1 style="margin:6px 0 0;font-size:22px;color:#fff">{'✅ Copy matched' if all_match else '❌ Copy not matched'}</h1>
          </td>
        </tr>

        <tr>
          <td style="padding:24px 32px">
            <p style="margin:0;color:#444;font-size:14px">
              Checked <a href="{url}" style="color:#1a1a1a">{url}</a> at {now}.
              {'All fields match your saved copy.' if all_match else 'Some fields do not match — see below.'}
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding:0 32px 28px">
            <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e5e5;border-radius:6px;border-collapse:collapse;font-size:14px">
              <tr style="background:#f9f9f9">
                <th style="padding:10px 12px;text-align:left;color:#888;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:0.5px"></th>
                <th style="padding:10px 12px;text-align:left;color:#888;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:0.5px">Live</th>
                <th style="padding:10px 12px;text-align:left;color:#888;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:0.5px">Saved</th>
              </tr>
              {rows}
            </table>
          </td>
        </tr>

        <tr>
          <td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eee">
            <p style="margin:0;font-size:12px;color:#aaa">You will only be notified when the live copy matches your saved copy. Green = matches. Red = does not match.</p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_bulk_match_email(matches: list) -> str:
    """Email for bulk mode — only shows URLs that matched."""
    now = datetime.now().strftime("%d %b %Y, %H:%M")
    count = len(matches)

    sections = ""
    for m in matches:
        url, live, saved = m["url"], m["live"], m["saved"]
        rows = ""
        for key, label in [("title", "Title"), ("meta_description", "Meta description"), ("intro_copy", "Intro copy"), ("h1", "H1")]:
            rows += f"""
            <tr>
              <td style="padding:8px 12px;font-weight:600;color:#555;white-space:nowrap;vertical-align:top;width:140px">{label}</td>
              <td style="padding:8px 12px;color:#222;vertical-align:top">{live.get(key, '')}</td>
              <td style="padding:8px 12px;background:#edfaf1;color:#1a7a3e;vertical-align:top">{saved.get(key, '')}</td>
            </tr>"""
        sections += f"""
        <div style="margin-bottom:20px;border:1px solid #e5e5e5;border-radius:6px;overflow:hidden">
          <div style="background:#1e3a1e;padding:10px 16px">
            <span style="color:#fff;font-weight:bold;font-size:13px">✅ {url}</span>
          </div>
          <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;border-collapse:collapse">
            <tr style="background:#f9f9f9">
              <th style="padding:8px 12px;text-align:left;color:#888;font-size:11px;text-transform:uppercase;width:140px">Field</th>
              <th style="padding:8px 12px;text-align:left;color:#888;font-size:11px;text-transform:uppercase">Live</th>
              <th style="padding:8px 12px;text-align:left;color:#888;font-size:11px;text-transform:uppercase">Your Saved Copy</th>
            </tr>{rows}
          </table>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)">
        <tr>
          <td style="background:#1a1a1a;padding:28px 32px">
            <p style="margin:0;font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:1px">Site Monitor — Bulk Notification</p>
            <h1 style="margin:6px 0 0;font-size:22px;color:#fff">✅ {count} URL{'s' if count > 1 else ''} matched</h1>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 32px 4px">
            <p style="margin:0;color:#444;font-size:14px">Checked at {now}. The following URLs now match your saved copy.</p>
          </td>
        </tr>
        <tr><td style="padding:16px 32px 28px">{sections}</td></tr>
        <tr>
          <td style="padding:16px 32px;background:#f9f9f9;border-top:1px solid #eee">
            <p style="margin:0;font-size:12px;color:#aaa">You will only be notified once per URL until the copy changes and matches again.</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _run_single(cfg: dict, state: dict):
    url = cfg["url"]
    saved = cfg.get("saved_copy", {})
    log(f"Checking {url}")
    try:
        live = fetch_copy(url)
    except Exception as e:
        log(f"ERROR fetching page: {e}")
        return

    log(f"Live title:       {live['title']}")
    log(f"Live description: {live['meta_description']}")
    log(f"Live intro:       {live['intro_copy']}")
    log(f"Live H1:          {live['h1']}")

    all_match, mismatches = fields_match(live, saved)
    if all_match:
        if state.get("notified"):
            log("Copy still matches — notification already sent, skipping.")
        else:
            log("MATCH — sending notification email.")
            body = build_email_body(url, live, saved, True)
            try:
                send_email(cfg, f"[Site Monitor] ✅ Copy is live — {url}", body)
                log("Email sent.")
                state["notified"] = True
                save_json(STATE_FILE, state)
            except Exception as e:
                log(f"ERROR sending email: {e}")
    else:
        log(f"No match yet. Mismatched fields: {', '.join(mismatches)}")
        if state.get("notified"):
            state["notified"] = False
            save_json(STATE_FILE, state)


def _run_bulk(cfg: dict, state: dict):
    bulk_urls = cfg.get("bulk_urls", [])
    if not bulk_urls:
        log("Bulk mode but no URLs configured.")
        return

    notified_urls = state.get("notified_urls", {})
    new_matches = []

    for item in bulk_urls:
        url = item.get("url", "").strip()
        if not url:
            continue
        saved = {
            "title": item.get("title", "").strip(),
            "meta_description": item.get("meta_description", "").strip(),
            "intro_copy": item.get("intro_copy", "").strip(),
            "h1": item.get("h1", "").strip(),
        }
        log(f"Checking {url}")
        try:
            live = fetch_copy(url)
        except Exception as e:
            log(f"  ERROR: {e}")
            continue

        log(f"  title: {live['title']}")
        log(f"  description: {live['meta_description']}")
        log(f"  intro: {live['intro_copy']}")
        log(f"  h1: {live['h1']}")

        all_match, mismatches = fields_match(live, saved)
        if all_match:
            if notified_urls.get(url):
                log("  MATCH (already notified — skipping)")
            else:
                log("  MATCH — will notify")
                new_matches.append({"url": url, "live": live, "saved": saved})
                notified_urls[url] = True
        else:
            log(f"  No match. Mismatched: {', '.join(mismatches)}")
            if notified_urls.get(url):
                notified_urls[url] = False  # reset so we notify again if it matches later

    state["notified_urls"] = notified_urls
    save_json(STATE_FILE, state)

    if new_matches:
        log(f"Sending email for {len(new_matches)} new match(es).")
        html = build_bulk_match_email(new_matches)
        subj = f"[Site Monitor] ✅ {len(new_matches)} URL{'s' if len(new_matches) > 1 else ''} matched"
        try:
            send_email(cfg, subj, html)
            log("Email sent.")
        except Exception as e:
            log(f"ERROR sending email: {e}")
    else:
        log("No new matches this run.")


def main():
    cfg = load_json(CONFIG_FILE)
    if not cfg:
        print("config.json not found or empty. Exiting.")
        sys.exit(1)

    state = load_json(STATE_FILE, default={})
    mode = cfg.get("mode", "single")
    log(f"Mode: {mode}")

    if mode == "bulk":
        _run_bulk(cfg, state)
    else:
        _run_single(cfg, state)


if __name__ == "__main__":
    main()
