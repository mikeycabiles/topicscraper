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
    # General AI signal
    ("Anthropic",       "https://www.anthropic.com/news/rss.xml"),
    ("MIT Tech Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("VentureBeat AI",  "https://venturebeat.com/category/ai/feed/"),
    ("TechCrunch AI",   "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI",    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"),
    ("Hacker News",     "https://hnrss.org/frontpage"),
    ("Simon Willison",  "https://simonwillison.net/atom/everything/"),
    ("The Decoder",     "https://the-decoder.com/feed/"),
    # ICP-aligned: tool blogs + marketing/operator AI digests
    ("Zapier Blog",     "https://zapier.com/blog/feeds/latest/"),
    ("HubSpot Marketing", "https://blog.hubspot.com/marketing/rss.xml"),
    ("Buffer",          "https://buffer.com/resources/feed/"),
    ("Beehiiv Blog",    "https://blog.beehiiv.com/feed"),
    ("Ben's Bites",     "https://bensbites.beehiiv.com/feed"),
    ("Marketing AI Institute", "https://www.marketingaiinstitute.com/blog/rss.xml"),
]

LOOKBACK_HOURS   = 24
MAX_STORIES      = 5
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

    prompt = f"""You are researching AI news for a SOLO MARKETING CONSULTANT earning $10K-$50K/month with an active online audience. Their goal: (a) implement AI in their own marketing and operations to free up time, and (b) productize AI workflows as offers they sell to their clients.

ICP details:
- Solo decision-maker, not a corporate team
- Strong online presence — actively posts, runs an email list, has a paid offer
- Niche bias: marketing consultants/coaches/course creators/agency owners and adjacent solo service providers
- Already uses ChatGPT or Claude for surface tasks (drafting blog posts, email subject lines)
- Has NOT systematized AI in their operations or productized AI as a client offer
- Buys based on: operator credibility, specific implementation, ROI clarity

A story qualifies ONLY if ALL are true:
1. Implementable by a non-engineer in under 2 weeks
2. Total tooling cost under $1,000/month
3. Marketing or operations application is direct (not "could be applied to marketing")
4. Has an obvious productized service angle ("you could sell this to your clients as ___")
5. Doesn't require infrastructure (no servers, no ML pipelines, no fine-tuning)

AUTO-REJECT:
- Frontier model research, benchmarks, or capability announcements (unless they unlock a specific marketer workflow)
- Enterprise / Fortune 500 case studies
- AI safety, policy, or regulation
- Model comparisons (e.g. GPT-5 vs Claude 4.5)
- Funding / M&A news
- Technical infrastructure (vector DBs, RAG, fine-tuning, deployment)
- Anything about "agents" framed as a developer concept rather than a business outcome

AUTO-PRIORITIZE:
- New AI features in tools the ICP already uses (HubSpot, Klaviyo, ActiveCampaign, Notion, Airtable, Make, Zapier, ConvertKit/Kit, Beehiiv, Buffer, Webflow, Framer)
- Prompt patterns that change a marketing or ops workflow (voice cloning, brand voice files, customer research, ad copy frameworks)
- Custom GPTs / Claude Projects with a specific business job
- Voice/clone tech for content scaling (HeyGen, ElevenLabs, OpusClip)
- Ad creative automation (Meta, Google, paid social)
- AI for customer research, VOC mining, review analysis
- Integration recipes (e.g. Claude + Zapier to do X)
- Workflow case studies from solo operators
- AI features in CRM/email tools that automate sales touchpoints

BRAND VOICE — angles must sound like the operator, not a tech reporter or guru:
- "Always grateful, never content" — Ambitious Underdog energy
- Raw and real, no filter. Speak as a peer, not a teacher condescending down.
- Direct, declarative sentences. No hedging.
- No corporate-speak (no "leverage," "synergy," "optimize"). Use verbs ("use," "run," "ship").
- Keep "I" or "we" present in opinionated takes.
- Mid-level altitude: assume reader knows what ChatGPT is, not what a "system prompt" is.
- WRONG: "How AI agents are revolutionizing the marketing operations stack."
- RIGHT: "How a $97/mo Claude Project replaces three hires for a solo marketing consultant — and the prompt I'd build first."

Return between 3 and {MAX_STORIES} stories from the {LOOKBACK_HOURS}h signal pool below. If fewer than 3 qualify, return what you have and START the output with `*Pull was thin today.*` on its own line — DO NOT pad with off-target stories.

For EACH qualifying story, output in this EXACT format (single asterisks for Telegram bold; no `#`; separate stories with `---` on its own line):

🔥 *[STORY HEADLINE — written as a hook, not a tech-news title]*
🔗 [URL]

*THE SIGNAL* — what actually happened:
[2-3 sentences, plain language, no jargon]

*WHY IT MATTERS FOR YOU:*
[2-3 sentences. Use "you" and "your clients." Show the implication for THEIR business or THEIR offer.]

*THE PRODUCTIZED ANGLE:*
[1-2 sentences answering: "What could you sell to your clients because of this?" Be specific — name the offer and a price point.]

*CONTENT ANGLE* (pick ONE, the strongest):
- Format: [LinkedIn post | X thread | IG Reel | YouTube long-form]
- Hook: [Specific opening line — must work as a thumb-stopper]
- Promise: [What the audience learns by the end]
- Framework: [The 3-5 beats the content will hit]

*SCRIPT-READY:* ✅  (or ⚠️ followed by what's missing)

NO preamble, NO sign-off — start directly with the first story (or with `*Pull was thin today.*`).

Signals:
{article_block}
"""

    msg = client.messages.create(
        model=MODEL,
        max_tokens=3500,
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
