# agent_logic.py
# جستجو با Google HTML (بدون API) + fallback به DuckDuckGo
# سپس اسکن سایت‌ها و صفحات تماس برای ایمیل/تلفن.
import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8"
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s()]{6,}\d)")

def fetch_html(url, params=None, timeout=25):
    r = requests.get(url, params=params or {}, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text

# ---------- جستجوگرها ----------
def google_search(query, num=6):
    """
    تلاش برای خواندن نتایج ارگانیک گوگل از HTML.
    ترفندها: hl/gl/fa، udm=14 (ساده‌تر)، tbs=li:1 (لینک مستقیم بیشتر)
    """
    params = {
        "q": f"{query} تامین کننده تولیدکننده فروش عمده تماس",
        "hl": "fa",
        "gl": "ir",
        "num": 20,     # زیاد می‌گیریم، بعد فیلتر می‌کنیم
        "udm": "14",
        "tbs": "li:1"
    }
    html = fetch_html("https://www.google.com/search", params=params)
    soup = BeautifulSoup(html, "lxml")
    links = []

    # روش 1: برداشت لینک‌های ارگانیک عمومی
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        text = (a.get_text(" ", strip=True) or "")
        # حذف لینک‌های داخلی گوگل و چیزهای نامرتبط
        if not href.startswith("http"):
            continue
        bad = ("google.", "/search?", "policies.google", "support.google", "accounts.google",
               "maps.google", "translate.google", "webcache.google")
        if any(b in href for b in bad):
            continue
        # کمی فیلتر بر اساس متن
        if text and len(text) < 2:
            continue
        links.append({"title": text[:120] or href, "url": href})
        if len(links) >= num:
            break

    # اگر چیزی نیامد، روش 2: div.g
    if not links:
        for g in soup.select("div.g a[href]"):
            href = g.get("href", "")
            if href.startswith("http") and "google." not in href:
                title = g.get_text(" ", strip=True)
                links.append({"title": title[:120] or href, "url": href})
                if len(links) >= num:
                    break
    return links

def ddg_search(query, num=6):
    """Fallback: برداشتن لینک‌ها از DuckDuckGo HTML."""
    q = urllib.parse.quote_plus(f"{query} supplier manufacturer contact")
    html = fetch_html(f"https://duckduckgo.com/html/?q={q}")
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select(".result__a"):
        href = a.get("href")
        title = a.get_text(" ", strip=True)
        if href and href.startswith("http"):
            out.append({"title": title[:120] or href, "url": href})
            if len(out) >= num:
                break
    return out

# ---------- ابزارهای کمکی ----------
def absolute(base, href):
    return urllib.parse.urljoin(base, href)

def extract_contacts_from_html(html):
    emails = set(EMAIL_RE.findall(html))
    phones = set(PHONE_RE.findall(html))
    return {
        "email": next(iter(emails), None),
        "phone": next(iter(phones), None),
        "whatsapp": next(iter(phones), None)  # ساده: همان شماره را واتساپ فرض می‌کنیم
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
        if u not in uniq:
            uniq.append(u)
    return uniq[:6]

def guess_name(soup):
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)[:120]
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)[:120]
    og = soup.find("meta", attrs={"property":"og:site_name"})
    if og and og.get("content"):
        return og["content"][:120]
    return ""

def scrape_site(url):
    out = {"name":"", "country":None, "products":[], "contacts":{}, "source":url, "note":""}
    try:
        html = fetch_html(url, timeout=30)
    except Exception as e:
        out["note"] = f"بارگذاری نشد: {e}"
        return out
    soup = BeautifulSoup(html, "lxml")
    out["name"] = guess_name(soup)
    out["contacts"] = extract_contacts_from_html(html)

    # صفحات تماس/درباره
    for p in find_contact_links(url, soup):
        time.sleep(1)  # مودبانه
        try:
            h = fetch_html(p, timeout=20)
        except Exception:
            continue
        c = extract_contacts_from_html(h)
        for k, v in c.items():
            if v and not out["contacts"].get(k):
                out["contacts"][k] = v

    # محصولات: از meta description
    meta = soup.find("meta", attrs={"name":"description"})
    if meta and meta.get("content"):
        out["products"] = [meta["content"][:200]]
    return out

# ---------- نقطه ورود اصلی ----------
def find_suppliers(query: str):
    # سعی با گوگل؛ اگر نشد، fallback
    sites = []
    try:
        sites = google_search(query, num=6)
    except Exception:
        sites = []
    if not sites:
        try:
            sites = ddg_search(query, num=6)
        except Exception:
            sites = []

    if not sites:
        return [{
            "name": "نتیجه‌ای از موتورهای جست‌وجو پیدا نشد.",
            "country": None, "products": [], "contacts": {},
            "source": "", "note": "ممکن است گوگل موقتاً محدود کرده باشد. بعداً امتحان کنید یا عبارت را تغییر دهید."
        }]

    results = []
    for s in sites:
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
    return results
