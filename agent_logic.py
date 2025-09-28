# agent_logic.py — با گزارش دیباگ و فیلترهای شُل‌تر
import re, time, random, urllib.parse
import requests
from bs4 import BeautifulSoup

# ===== تنظیمات سریع =====
MAX_SITES = 12                 # چند سایت اسکن کنیم
PAUSE_SEC = (0.4, 0.9)         # مکث مودبانه
REQUIRE_PERSIAN = False        # فعلاً غیرفعال تا نتایج بیشتر بیاید
STRICT_IR = False              # فعلاً فقط .ir نباشد

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

# ===== ابزار عمومی =====
def fetch_html(url, params=None, timeout=25):
    r = requests.get(url, params=params or {}, headers=H(), timeout=timeout)
    r.raise_for_status()
    return r.text

def fetch_soft(url, timeout=25):
    time.sleep(random.uniform(*PAUSE_SEC))
    return fetch_html(url, timeout=timeout)

def absolute(base, href):
    return urllib.parse.urljoin(base, href)

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

def extract_contacts_from_html(html):
    emails = set(EMAIL_RE.findall(html))
    phones = set(PHONE_RE.findall(html))
    wa = set()
    if "wa.me" in html or "whatsapp" in html.lower() or "واتساپ" in html:
        wa.update(phones)
    return {
        "email": next(iter(emails), None),
        "phone": next(iter(phones), None),
        "whatsapp": next(iter(wa), None)
    }

def find_contact_links(base_url, soup):
    keys = ["contact","تماس","درباره","ارتباط","تماس با ما","ارتباط با ما","contact-us","about"]
    found = []
    for a in soup.find_all("a", href=True):
        text = (a.get_text(" ", strip=True) or "").lower()
        href = a["href"].lower()
        if any(k in text for k in keys) or any(k in href for k in keys):
            found.append(absolute(base_url, a["href"]))
    uniq = []
    for u in found:
        if u not in uniq: uniq.append(u)
    return uniq[:8]

def guess_name(soup):
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True): return h1.get_text(strip=True)[:120]
    if soup.title and soup.title.get_text(strip=True): return soup.title.get_text(strip=True)[:120]
    og = soup.find("meta", attrs={"property":"og:site_name"})
    if og and og.get("content"): return og["content"][:120]
    return ""

def scrape_site(url):
    out = {"name":"", "country":None, "products":[], "contacts":{}, "source":url, "note":""}
    try:
        html = fetch_soft(url, timeout=30)
    except Exception as e:
        out["note"] = f"بارگذاری نشد: {e}"
        return out

    if REQUIRE_PERSIAN and not is_persian(html):
        out["note"] = "صفحه فارسی نبود/کم‌متن فارسی داشت"
        return out

    soup = BeautifulSoup(html, "lxml")
    out["name"] = guess_name(soup)
    out["contacts"] = extract_contacts_from_html(html)

    # صفحات تماس/درباره
    for p in find_contact_links(url, soup):
        try:
            h = fetch_soft(p, timeout=20)
            c = extract_contacts_from_html(h)
            for k, v in c.items():
                if v and not out["contacts"].get(k):
                    out["contacts"][k] = v
        except Exception:
            continue

    # محصولات: از meta description
    meta = soup.find("meta", attrs={"name":"description"})
    if meta and meta.get("content"):
        out["products"] = [meta["content"][:200]]
    return out

# ===== موتورهای جستجو (بدون API) =====
def google_search(query, want=25):
    # چند ترفند برای افزایش شانس بدون API
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

def ddg_search(query, want=25):
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

def qwant_search(query, want=25):
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
    # ترتیب: گوگل → داک‌داک → کوانت
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
        url = it["url"].split("#")[0]
        if not is_allowed(url): continue
        if url in seen: continue
        seen.add(url); out.append(it)
        if len(out) >= limit: break
    return out

# ===== ساخت کوئری‌ها =====
def build_queries(q):
    q = q.strip()
    return [
        f"{q} تامین کننده تماس ایمیل",
        f"{q} تولیدکننده تماس",
        f"{q} عمده تماس",
        f"{q} supplier manufacturer contact email",
        f"{q} distributor wholesaler contact email",
        f"{q} site:.ir تامین کننده تماس",
    ]

# ===== نقطهٔ ورود اصلی =====
def find_suppliers(query: str):
    queries = build_queries(query)
    links = []
    for q in queries:
        try:
            links += multi_search(q)
        except Exception:
            continue
    links = dedup(links, limit=MAX_SITES * 2)
    if not links:
        return []

    results = []
    for s in links[:MAX_SITES]:
        try:
            item = scrape_site(s["url"])
            if not item["name"]:
                item["name"] = s.get("title") or s["url"]
            results.append(item)
        except Exception as e:
            results.append({
                "name": s.get("title") or s.get("url"),
                "country": None, "products": [], "contacts": {},
                "source": s["url"], "note": f"خطا در اسکرپ: {e}"
            })
    # اولویت به نتایج دارای راه تماس
    def has_contact(x):
        c = x.get("contacts") or {}
        return any([c.get("email"), c.get("phone"), c.get("whatsapp")])
    results.sort(key=lambda x: (not has_contact(x), x.get("name") or ""))
    return results

# ===== گزارش دیباگ: فقط لینک‌های جمع‌آوری شده =====
def debug_collect(query: str):
    qs = build_queries(query)
    report = {"query": query, "tries": [], "picked": []}
    pool = []
    for q in qs:
        try:
            lst = multi_search(q)
            report["tries"].append({"q": q, "count": len(lst)})
            pool += lst
        except Exception as e:
            report["tries"].append({"q": q, "error": str(e)})
    picked = dedup(pool, limit=MAX_SITES * 2)
    report["picked"] = picked
    return report
