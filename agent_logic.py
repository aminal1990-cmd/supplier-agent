# agent_logic.py
# جستجو با Google (بدون API) روی دامنه‌های .ir + اسکن صفحه تماس برای ایمیل/تلفن
import re, time, random, urllib.parse
import requests
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36",
]
BAD_HOST_FRAGMENTS = (
    "google.", "webcache.google", "maps.google", "translate.google",
    "facebook.", "twitter.", "linkedin.", "instagram.", "youtube.", "t.me/", "telegram."
)

def H():  # headers
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
    if not d.endswith(".ir"): return False             # فقط دامنه‌های ایرانی
    if any(b in d for b in BAD_HOST_FRAGMENTS): return False
    return True

def is_persian(html):
    # حداقل چند ده کاراکتر فارسی وجود داشته باشد
    return len(PERSIAN_RE.findall(html)) >= 40

# ---------- ساخت کوئری‌های دقیق ----------
def build_queries(q):
    q = q.strip()
    base = [
        f"{q} تامین کننده site:.ir تماس ایمیل",
        f"{q} تولیدکننده site:.ir تماس",
        f"{q} عمده site:.ir تماس",
        f"{q} شرکت site:.ir تماس",
        f"{q} فروشنده site:.ir تماس ایمیل",
    ]
    # اگر انگلیسی هم بود
    base += [f"{q} supplier site:.ir contact email"]
    return base

# ---------- جستجوی گوگل (بدون API) ----------
def google_search_raw(query, want=10):
    params = {
        "q": query,
        "hl": "fa", "gl": "ir",
        "num": 20, "udm": "14", "tbs": "li:1"
    }
    html = fetch_html("https://www.google.com/search", params=params)
    soup = BeautifulSoup(html, "lxml")
    out = []
    # روش عمومی روی همه <a>
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href.startswith("http"): continue
        if any(b in href for b in BAD_HOST_FRAGMENTS): continue
        t = (a.get_text(" ", strip=True) or "").strip()
        if not t: continue
        out.append({"title": t[:120], "url": href})
        if len(out) >= want: break
    # fallback div.g
    if not out:
        for g in soup.select("div.g a[href]"):
            href = g.get("href", "")
            if href.startswith("http") and not any(b in href for b in BAD_HOST_FRAGMENTS):
                t = g.get_text(" ", strip=True)
                out.append({"title": (t[:120] or href), "url": href})
                if len(out) >= want: break
    return out

def dedup_keep_ir(items, limit=12):
    seen, out = set(), []
    for it in items:
        u = it["url"].split("#")[0]
        if not is_allowed(u):  # فقط .ir و بدون شبکه‌های اجتماعی
            continue
        if u in seen: continue
        seen.add(u); out.append(it)
        if len(out) >= limit: break
    return out

# ---------- ابزارهای کمکی ----------
def absolute(base, href):
    return urllib.parse.urljoin(base, href)

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
    return uniq[:6]

def guess_name(soup):
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True): return h1.get_text(strip=True)[:120]
    if soup.title and soup.title.get_text(strip=True): return soup.title.get_text(strip=True)[:120]
    og = soup.find("meta", attrs={"property":"og:site_name"})
    if og and og.get("content"): return og["content"][:120]
    return ""

def fetch_soft(url, timeout=25):
    time.sleep(random.uniform(0.5, 1.0))  # مودبانه
    return fetch_html(url, timeout=timeout)

def scrape_site(url):
    out = {"name":"", "country":"ایران", "products":[], "contacts":{}, "source":url, "note":""}
    try:
        html = fetch_soft(url, timeout=30)
    except Exception as e:
        out["note"] = f"بارگذاری نشد: {e}"
        return out
    # فقط صفحات فارسی را نگه می‌داریم
    if not is_persian(html):
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

# ---------- نقطه ورود ----------
def find_suppliers(query: str):
    # چند کوئری می‌سازیم و نتایج را ادغام/فیلتر می‌کنیم
    links = []
    for q in build_queries(query):
        try:
            links += google_search_raw(q, want=12)
        except Exception:
            continue
    links = dedup_keep_ir(links, limit=12)
    if not links:
        return [{
            "name": "موردی در .ir پیدا نشد",
            "country": "ایران", "products": [], "contacts": {},
            "source": "", "note": "عبارت را تغییر دهید (مثلاً «تماس»، «ایمیل»، «عمده»، شهر/استان)."
        }]

    results = []
    for s in links[:10]:  # تا ۱۰ سایت اول را اسکن کن
        try:
            item = scrape_site(s["url"])
            if not item["name"]:
                item["name"] = s.get("title") or s["url"]
            results.append(item)
        except Exception as e:
            results.append({
                "name": s.get("title") or s.get("url"),
                "country": "ایران", "products": [], "contacts": {},
                "source": s["url"], "note": f"خطا در اسکرپ: {e}"
            })
    # نتایج خالی از تماس را آخر لیست بفرست
    results.sort(key=lambda x: (not any(x.get("contacts", {}).values()), x.get("name") or ""))
    return results
