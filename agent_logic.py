# agent_logic.py
# چند موتور جستجو (Google → DuckDuckGo → Qwant) بدون API + اسکن صفحات تماس
import re, time, random, urllib.parse
import requests
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36",
]
def headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s()]{6,}\d)")

def fetch_html(url, params=None, timeout=25):
    r = requests.get(url, params=params or {}, headers=headers(), timeout=timeout)
    r.raise_for_status()
    return r.text

# ========== جستجوگرها ==========
def google_search(query, num=6):
    params = {
        "q": f"{query} تامین کننده تولیدکننده فروش عمده تماس email site:.ir",
        "hl": "fa",
        "gl": "ir",
        "num": 20,
        "udm": "14",
        "tbs": "li:1"
    }
    html = fetch_html("https://www.google.com/search", params=params)
    soup = BeautifulSoup(html, "lxml")
    links = []
    bad = ("google.", "/search?", "policies.google", "support.google", "accounts.google",
           "maps.google", "translate.google", "webcache.google")
    # روش عمومی
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href.startswith("http"): continue
        if any(b in href for b in bad): continue
        text = (a.get_text(" ", strip=True) or "")
        if text and len(text) < 2: continue
        links.append({"title": text[:120] or href, "url": href})
        if len(links) >= num: break
    # fallback div.g
    if not links:
        for g in soup.select("div.g a[href]"):
            href = g.get("href", "")
            if href.startswith("http") and "google." not in href:
                title = g.get_text(" ", strip=True)
                links.append({"title": title[:120] or href, "url": href})
                if len(links) >= num: break
    return links

def ddg_search(query, num=6):
    q = urllib.parse.quote_plus(f"{query} supplier manufacturer contact email")
    html = fetch_html(f"https://duckduckgo.com/html/?q={q}")
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select(".result__a")[:num*2]:
        href = a.get("href")
        title = a.get_text(" ", strip=True)
        if href and href.startswith("http"):
            out.append({"title": title[:120] or href, "url": href})
        if len(out) >= num: break
    return out

def qwant_search(query, num=6):
    q = urllib.parse.quote_plus(f"{query} contact email supplier site:.ir")
    html = fetch_html(f"https://www.qwant.com/?q={q}&t=web")
    soup = BeautifulSoup(html, "lxml")
    out = []
    # نتایج ساده: لینک‌های خارجی داخل نتایج
    for a in soup.select("a[href^='http']"):
        href = a.get("href")
        txt = a.get_text(" ", strip=True)
        if href and "qwant.com" not in href and txt:
            out.append({"title": txt[:120], "url": href})
        if len(out) >= num: break
    return out

def multi_search(query, num=6):
    # ترتیب: گوگل → داک‌داک → کوانت
    for func in (google_search, ddg_search, qwant_search):
        try:
            links = func(query, num=num)
            if links: return dedup(links, num)
        except Exception:
            continue
    return []

def dedup(items, limit):
    seen, out = set(), []
    for it in items:
        url = it["url"].split("#")[0]
        if url in seen: continue
        seen.add(url); out.append(it)
        if len(out) >= limit: break
    return out

# ========== ابزارها ==========
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

def fetch_page_soft(url, timeout=30):
    # با وقفه‌ی رندوم برای جلوگیری از بلاک شدن
    time.sleep(random.uniform(0.6, 1.2))
    return fetch_html(url, timeout=timeout)

def scrape_site(url):
    out = {"name":"", "country":None, "products":[], "contacts":{}, "source":url, "note":""}
    try:
        html = fetch_page_soft(url, timeout=30)
    except Exception as e:
        out["note"] = f"بارگذاری نشد: {e}"
        return out
    soup = BeautifulSoup(html, "lxml")
    out["name"] = guess_name(soup)
    out["contacts"] = extract_contacts_from_html(html)

    # صفحات تماس/درباره
    for p in find_contact_links(url, soup):
        try:
            h = fetch_page_soft(p, timeout=20)
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

# ========== نقطه ورود ==========
def find_suppliers(query: str):
    # کلیدواژه را کمی غنی‌تر می‌کنیم تا شانس تماس/ایمیل بالا برود
    smart_query = query.strip()
    if "تماس" not in smart_query and "contact" not in smart_query.lower():
        smart_query += " تماس email"
    sites = multi_search(smart_query, num=6)
    if not sites:
        return [{
            "name": "نتیجه‌ای از موتورهای جست‌وجو پیدا نشد.",
            "country": None, "products": [], "contacts": {},
            "source": "", "note": "ممکن است موتور جست‌وجو موقتاً محدود کرده باشد. چند دقیقه بعد یا با عبارت دیگر امتحان کنید."
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
