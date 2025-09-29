import re, requests, time, random, urllib.parse
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote

# مرورگرهای تصادفی برای جلوگیری از بلاک شدن
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
]

# دامنه‌هایی که نباید در نتایج باشند (لینک داخلی موتورهای جستجو و شبکه‌های اجتماعی)
BLOCKED_HOST_FRAGS = (
    "startpage.", "duckduckgo.", "google.", "bing.", "yahoo.",
    "facebook.", "twitter.", "instagram.", "linkedin.", "youtube.",
    "t.me", "telegram.", "wikipedia.org"
)

def H():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fa,en;q=0.8"
    }

def fetch(url, params=None, timeout=20):
    return requests.get(url, params=params, headers=H(), timeout=timeout).text

def host(u):
    return (urlparse(u).hostname or "").lower()

def is_allowed(u, only_ir=True):
    h = host(u)
    if not h:
        return False
    # حذف دامنه‌های مسدود شده
    for bad in BLOCKED_HOST_FRAGS:
        if bad in h:
            return False
    # اگر فقط .ir بخواهیم
    if only_ir and not h.endswith(".ir"):
        return False
    return True

def extract_contacts(html):
    emails = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", html)
    phones = re.findall(r"(?:\+?98|0)?9\d{9}", html)
    return {
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None,
        "whatsapp": None
    }

def scrape_site(url):
    out = {"name": url, "contacts": {}, "source": url, "note": ""}
    try:
        html = fetch(url)
        out["contacts"] = extract_contacts(html)
        if "<title>" in html:
            out["name"] = BeautifulSoup(html, "lxml").title.get_text(strip=True)[:100]
    except Exception as e:
        out["note"] = str(e)
    return out

# --- پاک‌سازی لینک‌های موتورهای جستجو ---

def clean_startpage_href(h):
    try:
        p = urlparse(h)
        if "startpage.com" in (p.netloc or "") and p.path.startswith("/rd"):
            q = parse_qs(p.query)
            for k in ("url", "uddg"):
                if q.get(k):
                    return unquote(q[k][0])
    except:
        pass
    return h

def clean_ddg_href(h):
    try:
        p = urlparse(h)
        if (p.netloc or "").endswith("duckduckgo.com") and p.path.startswith("/l/"):
            q = parse_qs(p.query)
            if q.get("uddg"):
                return unquote(q["uddg"][0])
    except:
        pass
    return h

# --- موتورهای جستجو ---

def startpage_search(q, want=30, only_ir=True):
    base = "https://www.startpage.com"
    html = fetch(base + "/sp/search", params={"query": q, "language": "fa"})
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if href.startswith("/"):
            href = base + href
        href = clean_startpage_href(href)
        if not href.startswith("http"):
            continue
        if not is_allowed(href, only_ir):
            continue
        title = (a.get_text(" ", strip=True) or href)[:120]
        out.append({"title": title, "url": href})
        if len(out) >= want:
            break
    return out

def ddg_lite_search(q, want=30, only_ir=True):
    base = "https://duckduckgo.com"
    html = fetch("https://lite.duckduckgo.com/lite/", params={"q": q})
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if href.startswith("/"):
            href = base + href
        href = clean_ddg_href(href)
        if not href.startswith("http"):
            continue
        if not is_allowed(href, only_ir):
            continue
        title = (a.get_text(" ", strip=True) or href)[:120]
        if not title:
            continue
        out.append({"title": title, "url": href})
        if len(out) >= want:
            break
    return out

def mojeek_search(q, want=30, only_ir=True):
    base = "https://www.mojeek.com"
    html = fetch(base + "/search", params={"q": q})
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("ol.results li.result a[href]"):
        href = a.get("href") or ""
        if not href.startswith("http"):
            continue
        if not is_allowed(href, only_ir):
            continue
        title = (a.get_text(" ", strip=True) or href)[:120]
        out.append({"title": title, "url": href})
        if len(out) >= want:
            break
    return out

def google_search(q, want=20, only_ir=True):
    html = fetch("https://www.google.com/search", params={"q": q, "hl": "fa", "gl": "ir"})
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href^='http']"):
        href = a.get("href") or ""
        if "google." in href:
            continue
        if not is_allowed(href, only_ir):
            continue
        title = (a.get_text(" ", strip=True) or href)[:120]
        out.append({"title": title, "url": href})
        if len(out) >= want:
            break
    return out

# --- کنترل نهایی نتایج ---

def multi_search(q, engines):
    pool = []
    for e in engines:
        try:
            if e == "startpage":
                pool += startpage_search(q)
            elif e == "ddg_lite":
                pool += ddg_lite_search(q)
            elif e == "mojeek":
                pool += mojeek_search(q)
            elif e == "google":
                pool += google_search(q)
        except Exception as ex:
            continue
    return pool

def dedup(lst, limit):
    seen = set()
    out = []
    for it in lst:
        u = it["url"].split("#")[0]
        if u in seen:
            continue
        seen.add(u)
        out.append(it)
        if len(out) >= limit:
            break
    return out

def find_suppliers(query, limit=30, engine_order=("startpage","ddg_lite","mojeek","google")):
    pool = multi_search(query, engine_order)
    links = dedup(pool, limit*2)
    res = []
    for l in links[:limit]:
        res.append(scrape_site(l["url"]))
    return res

def debug_collect(query, limit=30, engine_order=("startpage","ddg_lite","mojeek","google")):
    rep = {"query": query, "tries": [], "picked": []}
    for e in engine_order:
        try:
            lst = multi_search(query, (e,))
            rep["tries"].append({"engine": e, "count": len(lst)})
        except Exception as ex:
            rep["tries"].append({"engine": e, "error": str(ex)})
    rep["picked"] = dedup(multi_search(query, engine_order), limit)
    return rep
