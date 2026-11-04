import calendar
import html
import logging
import os
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import feedparser

FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
    "Dark Reading": "https://www.darkreading.com/rss.xml",
    "SecurityWeek": "https://www.securityweek.com/feed/",
    "Schneier on Security": "https://www.schneier.com/feed/atom/",
    "CISA Advisories": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
    "Numerama": "https://www.numerama.com/cyberguerre/feed/",
    "The Record": "https://therecord.media/feed",
    "The Register": "https://www.theregister.com/security/headlines.atom",
    "SANS ISC": "https://isc.sans.edu/rssfeed_full.xml",
    "ZATAZ": "https://www.zataz.com/feed/",
}
PER_FEED = int(os.environ.get("PER_FEED", 8))
REFRESH_SECONDS = int(os.environ.get("REFRESH_MINUTES", 30)) * 60
DAYS = {"1": "Last 24 h", "3": "Last 3 days", "7": "Last week", "30": "Last month"}

log = logging.getLogger("news")
state = {"items": [], "updated": None}
images = {}  # link -> og:image URL; shortcut: in-memory, so a restart re-fetches article pages once


def clean(text, limit=None):
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()
    return text[:limit].rsplit(" ", 1)[0] + "…" if limit and len(text) > limit else text


def safe_link(url):
    # Feeds are untrusted: never render javascript:/data: links.
    return url if url and url.startswith(("https://", "http://")) else None


def feed_image(e, body):
    urls = [m.get("url") for m in e.get("media_content", []) + e.get("media_thumbnail", [])]
    urls += [l.get("href") for l in e.get("links", []) if l.get("rel") == "enclosure" and "image" in l.get("type", "")]
    urls += [html.unescape(u) for u in re.findall(r'<img[^>]+src="([^"]+)"', body)]
    return next((u for u in urls if u and u.startswith("https://")), None)


def page_image(link):
    # Some feeds carry no image: fall back to the article page's og:image (fetched once per article).
    if link not in images:
        try:
            req = urllib.request.Request(link, headers={"User-Agent": "news-checker/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                head = r.read(300_000).decode("utf-8", "replace")
            m = re.search(r'<meta[^>]+og:image"[^>]+content="([^"]+)"', head) or re.search(
                r'<meta[^>]+content="([^"]+)"[^>]+og:image"', head)
            url = html.unescape(m.group(1)) if m else None
            images[link] = url if url and url.startswith("https://") else None
        except OSError as ex:
            log.warning("no page image for %s: %s", link, ex)
            return None  # not cached, retried next refresh
    return images[link]


def fetch(source, url):
    feed = feedparser.parse(url, agent="news-checker/1.0")
    if not feed.entries:
        log.warning("no entries from %s (status %s)", source, feed.get("status"))
    items = []
    for e in feed.entries[:PER_FEED]:
        link = safe_link(e.get("link"))
        if not link:
            continue
        body = e.get("content", [{}])[0].get("value") or e.get("summary", "")
        when = e.get("published_parsed") or e.get("updated_parsed")
        items.append({
            "source": source,
            "title": clean(e.get("title")) or link,
            "link": link,
            "text": re.sub(r"\s*The post .* appeared first on .*$", "", clean(body)),  # WordPress feed footer
            "ts": calendar.timegm(when) if when else 0,
            "image": feed_image(e, body) or page_image(link),
        })
    return items


def refresh():
    with ThreadPoolExecutor(8) as pool:
        items = [i for batch in pool.map(lambda kv: fetch(*kv), FEEDS.items()) for i in batch]
    items.sort(key=lambda i: i["ts"], reverse=True)
    state.update(items=items, updated=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()))


def refresh_loop():
    while True:
        try:
            refresh()
        except Exception:
            log.exception("refresh failed")
        time.sleep(REFRESH_SECONDS)


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Cyber News</title>
<style>
:root{{--bg:#f1f8f3;--card:#fff;--fg:#14261a;--mute:#5b6f61;--accent:#15803d;--soft:#dcfce7}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0c1410;--card:#14201a;--fg:#e6f2ea;--mute:#8fa597;--accent:#4ade80;--soft:#163323}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:760px;margin:auto;padding:16px}}
h1{{color:var(--accent)}}
article{{background:var(--card);border-radius:8px;padding:14px 16px;margin:12px 0;border-left:4px solid var(--accent)}}
article img{{display:block;width:100%;max-height:240px;object-fit:cover;border-radius:6px;margin:8px 0}}
form{{background:var(--soft);border-radius:8px;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}}
label{{white-space:nowrap}} input{{accent-color:var(--accent)}} select{{font:inherit}}
button{{font:inherit;background:var(--accent);color:var(--card);border:0;border-radius:6px;padding:4px 14px;cursor:pointer}}
h2{{font-size:1.05rem;margin:4px 0}} .meta{{color:var(--mute);font-size:.85rem}}
a{{color:var(--accent)}} p{{margin:6px 0}}
</style></head><body><main><h1>Cybersecurity news</h1>
<form>{sources}<select name="days" aria-label="Date">{days}</select>
<button>Filter</button><a href="/">Reset</a></form>
<p class="meta">{status}</p>{articles}</main></body></html>"""

ARTICLE = """<article><div class="meta">{source} · {date}</div><h2>{title}</h2>{image}
<p>{summary}</p><a href="{link}" target="_blank" rel="noopener noreferrer">Read full article →</a></article>"""


def render(query=""):
    e = html.escape
    q = parse_qs(query)
    picked = set(q.get("source", [])) & FEEDS.keys()
    days = q.get("days", [""])[0]
    days = days if days in DAYS else ""
    since = time.time() - int(days) * 86400 if days else 0
    items = [i for i in state["items"] if (not picked or i["source"] in picked) and i["ts"] >= since]
    sources = "".join(
        f'<label><input type="checkbox" name="source" value="{e(s)}"{" checked" * (s in picked)}> {e(s)}</label>'
        for s in FEEDS
    )
    days_opts = "".join(
        f'<option value="{k}"{" selected" * (k == days)}>{v}</option>' for k, v in {"": "Any time", **DAYS}.items()
    )
    articles = "".join(
        ARTICLE.format(
            source=e(i["source"]),
            date=time.strftime("%Y-%m-%d %H:%M", time.gmtime(i["ts"])) if i["ts"] else "",
            title=e(i["title"]),
            summary=e(clean(i["text"], 300)),
            link=e(i["link"]),
            image=f'<img src="{e(i["image"])}" alt="" loading="lazy" referrerpolicy="no-referrer">' if i.get("image") else "",
        )
        for i in items
    )
    status = f"Updated {state['updated']} · {len(items)} articles" if state["updated"] else "Fetching feeds… reload in a minute."
    return PAGE.format(status=status, articles=articles, sources=sources, days=days_opts)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != "/":
            return self.send_error(404)
        body = render(url.query).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src https:")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    threading.Thread(target=refresh_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8000))), Handler).serve_forever()
