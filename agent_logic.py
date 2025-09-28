# agent_logic.py — نسخه Recall (گسترده) برای افزایش نتایج
import re, time, random, urllib.parse
import requests
from bs4 import BeautifulSoup

# ===== پیکربندی سریع =====
STRICT_IR = False          # اگر True شود فقط .ir می‌ماند؛ فعلاً False تا نتایج بیشتر بیاید
REQUIRE_PERSIAN = False    # اگر True شود فقط صفحاتِ خیلی فارسی می‌مانند؛ فعلاً False
MAX_SITES = 15             # چند سایت را اسکن کنیم
PAUSE_SEC = (0.4, 0.9)     # مکث مودبانه بین درخواست‌ها

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36",
]
BAD_HOST = (
    "google.", "webcache.google", "maps.google", "translate.google",
    "facebook.", "twitter.", "linkedin.", "instagram.", "youtube.", "t.me/", "telegram."
)

def H():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s()]{6,}\d)")
PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")

def fetch_html(url, params=None, timeout=25):
    r = requests.get(url, params=params or {}, headers=H(), timeout=timeout)
    r.raise_for_status()
    return r.text

def domain(url):
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "").lower()

def is_allowed(url):
    d = domain(url)
    if not d: return False
    if any(b in d for b in BAD_HOST): return False
    if STRICT_IR and not d.endswith(".ir"): return False
    return True

def is_persian(html):
    return len(PERSIAN_RE.findall(html)) >= 40

# ---------- ساخت کوئری‌ها (چند تنوع برای افزایش شانس) ----------
def build_queries(q):
    q = q.strip()
    qs = [
        f"{q} تامین کننده تماس ایمیل",
        f"{q} تولیدکننده تماس",
        f"{q} عمده تماس",
        f"{q} شرکت تماس",
        f"{q} قیمت تامین کننده تماس",
        f"{q} supplier manufacturer contact email",
        f"{q} distributor wholesaler contact email",
    ]
    # نسخه‌های site:.ir هم اضافه می‌کنیم اما اجباریش نمی‌کنیم
    qs += [f"{q} site:.ir تماس", f"{q} site:.ir تامین کننده"]
    return qs

# ---------- موتورهای جستجو (بدون API) ----------
def google_search(query, want=20):
    params = {"q": query, "hl": "fa", "gl": "ir", "num": 20, "udm": "14", "tbs": "li:1"}
    html = fetch_html("https://www.google.com/search", params=params)
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href.startswith("http"): continue
        if any(b in href for b in BAD_HOST): continue
        txt = (a.get_text(" ", strip=True) or "")
        if txt and len(txt) < 2: continue
        out.append({"title": txt[:120] or href, "url": href})
        if len(out) >= want: break
    if not out:
        for g in soup.select("div.g a[href]"):
            href = g.get("href", "")
            if href.startswith("http") and not any(b in href for b in BAD_HOST):
                t = g.get_text(" ", strip=True)
                out.append({"title": t[:120] or href, "url": href})
                if len(out) >= want: break
    return out

def ddg_search(query, want=20):
    q = urllib.parse.quote_plus(query)
    html = fetch_html(f"https://duckduckgo.com/html/?q={q}")
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select(".result__a"):
        href = a.get("href")
        title = a.get_text(" ", strip=True)
        if href and href.startswith("http"):
            out.append({"title": title[:120] or href, "url": href})
            if len(out) >= want: break
    return out

def qwant_search(query, want=20):
    q = urllib.parse.quote_plus(query)
    html = fetch_html(f"https://www.qwant.com/?q={q}&t=web")
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href^='http']"):
        href = a.get("href"); txt = a.get_text(" ", strip=True)
        if href and "qwant.com" not in href and txt:
            out.append({"title": txt[:120], "url": href})
            if len(out) >= want: break
    return out

def multi_search(query):
    for engine in (google_search, ddg_search, qwant_search):
        try:
            links = engine(query, want=25)
            if links: return links
        except Exception:
            continue
    return []

def dedup(items, limit):
    seen, out = set(), []
    for it in items:
        url = it["url"].s
