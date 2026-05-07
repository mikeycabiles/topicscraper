"""
Daily AI Brief
--------------
Pulls AI signal from a curated set of RSS sources, summarizes the top picks
with Claude Haiku 4.5 into specific content angles for an AI-systems
consulting personal brand, and sends the result to Telegram.
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
from anthropic import Anthropic

# ============================================================================
# CONFIG
# ============================================================================

RSS_FEEDS = [
    ("Anthropic",       "https://www.anthropic.com/news/rss.xml"),
    ("MIT Tech Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("VentureBeat AI",  "https://venturebeat.com/category/ai/feed/"),
    ("TechCrunch AI",   "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI",    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"),
    ("Hacker News",     "https://hnrss.org/frontpage"),
    ("Simon Willison",  "https://simonwillison.net/atom/everything/"),
    ("The Decoder",     "https://the-decoder.com/feed/"),
]

LOOKBACK_HOURS   = 24
TOP_N_STORIES    = 5
MAX_ITEMS_TO_LLM = 60
MODEL            = "claude-haiku-4-5-20251001"


# ============================================================================
# FETCH — RSS
# ============================================================================

def fetch_rss():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    out = []
    for source_name, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:15]:
                published = _parse_date(entry)
                if published and published < cutoff:
                    continue
                out.append({
                    "title":   entry.get("title", "Untitled"),
                    "link":    entry.get("link", ""),
                    "summary": _strip_html(entry.get("summary", "")),
                    "source":  source_name,
                    "score":   0,
                })
        except Exception as e:
            print(f"warn: RSS {source_name} failed — {e}", file=sys.stderr)
    return out


# ============================================================================
# HELPERS
# ============================================================================

def _parse_date(entry):
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                return parsedate_to_datetime(val).astimezone(timezone.utc)
            except Exception:
                pass
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            try:
                return datetime(*struct[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _strip_html(html):
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def dedupe(articles):
    seen, out = set(), []
    for a in articles:
        key = re.sub(r"\W+", "", a["title"].lower())[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


# ============================================================================
# SUMMARIZE
# ============================================================================

def summarize(articles):
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    article_block = "\n\n---\n\n".join(
        f"#{i+1}. {a['title']}\n"
        f"Source: {a['source']}\n"
        f"Link: {a['link']}\n"
        f"Snippet: {a['summary'][:500]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""You are a content strategist for an AI systems consultant who builds AI for businesses and teaches them how to use it.

Their content blends four styles:
- DOCUMENTING the build (Daniel Dalen, Fin Kwong) — "week N building X"
- EDUCATIONAL system-thinking (Dan Koe) — frameworks, principles, leverage
- TESTIMONIAL and proof-driven (Soowei Goh) — client wins, case studies
- BUILDER POV — "here's how I'd actually implement this for a client"

Audience: business owners considering AI, and ambitious operators/builders learning to deliver AI services.

Below are AI signals from the last {LOOKBACK_HOURS} hours across AI publications and developer feeds. Pick the TOP {TOP_N_STORIES} most CONTENT-WORTHY for this brand. Prioritize, in order:
1. Stories with a clear "how I'd implement this for a business" angle
2. Tools/techniques worth a build-along or teardown
3. Real adoption stories or contrarian takes the herd is missing

Avoid: pure research papers without business application, recycled hype, generic "AI is changing everything" takes.

For EACH of the {TOP_N_STORIES} stories, output in this EXACT format:

*[N]. [Punchy headline]*
🔗 [link]
*The signal:* 2 sentences max — what happened or what's being discussed.
*Why it matters for AI consultants:* 1 sentence.
*Content angle:* ONE specific deliverable. Pick a format and be concrete:
   - Tweet/X post (give the actual hook line)
   - Thread (give the premise + 1-line topic per post)
   - Reel/Short premise (give the on-screen hook)
   - YouTube long-form angle (give the title)
   - Or testimonial-style framing if there's a client-win parallel

Use Telegram markdown (single asterisks for bold; no #). Total output under 3500 characters. NO preamble, NO sign-off — start directly with story 1.

Signals:
{article_block}
"""

    msg = client.messages.create(
        model=MODEL,
        max_tokens=2200,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# ============================================================================
# DELIVER
# ============================================================================

def send_telegram(text):
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url     = f"https://api.telegram.org/bot{token}/sendMessage"

    for chunk in _chunk(text, 4000):
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=30)
        if not r.ok:
            print(f"warn: markdown send failed ({r.status_code}); retrying as plain text", file=sys.stderr)
            r = requests.post(url, json={"chat_id": chat_id, "text": chunk}, timeout=30)
            r.raise_for_status()


def _chunk(text, size):
    if len(text) <= size:
        return [text]
    chunks, current = [], ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 > size and current:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("fetching signals…")
    items = []
    items.extend(fetch_rss())

    items = dedupe(items)
    items.sort(key=lambda a: -a.get("score", 0))
    items = items[:MAX_ITEMS_TO_LLM]

    print(f"feeding {len(items)} items to {MODEL}")

    if not items:
        send_telegram("🤖 *AI Brief* — no fresh signals in the last 24h.")
        return

    summary = summarize(items)
    today   = datetime.now(timezone.utc).strftime("%A, %b %d")
    header  = f"🤖 *AI Brief — {today}*\n\n"
    send_telegram(header + summary)
    print("sent ✓")


if __name__ == "__main__":
    main()
