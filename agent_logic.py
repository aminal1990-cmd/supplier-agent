# agent_logic.py — هدفمند برای ایران + حداقل N نتیجه + جلوگیری از تکراری‌ها بین دفعات
import re, time, random, urllib.parse
import requests
from bs4 import BeautifulSoup

# ===== تنظیمات عمومی =====
STRICT_IR       = True            # فقط دامنه‌های .ir
REQUIRE_PERSIAN = True            # فقط صفحات با متن فارسی کافی
PAUSE_RANGE_SEC = (0.45, 1.1)     # مکث مودبانه
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
]
BLOCKED_HOST_FRAGS = (
    "google.", "webcache.google", "maps.google", "translate.google", "accounts.google",
    "duckduckgo.", "qwant.", "bing.", "yahoo.",
    "facebook.", "twitter.", "linkedin.", "instagram.", "youtube.", "t.me/", "telegram."
)

# ===== الگوها =====
PERSIAN_RE   = re.compile(r"[\u0600-\u06FF]")
EMAIL_RE     = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I)
IR_MOBILE    = re.compile(r"^(?:\+?98|0)?9\d{9}$")
IR_LANDLINE  = re.compile(r"^(?:\+?98|0)\d{9,10}$")

# ===== ابزار =====
def H():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

def sleep_soft():
    time.sleep(random.uniform(*PAUSE_RANGE_SEC))

def fetch_html(url, params=None, timeout=25):
    r = requests.get(url, params=params or {}, headers=H(), timeout=timeout)
    r.raise_for_status()
    return r.text

def fetch_soft(url, timeout=25):
    sleep_soft()
    return fetch_html(url, timeout=timeout)

def absolute(base, href):
    return urllib.parse.urljoin(base, href)

def hostname(url):
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "").lower()

def is_allowed_url(url: str) -> bool:
    h = hostname(url)
    if not h: return False
    if any(bad in h for bad in BLOCKED_HOST_FRAGS): return False
    if STRICT_IR and not h.endswith(".ir"): return False
    return True

def is_persian_enough(html: str) -> bool:
    return len(PERSIAN_RE.findall(html)) >= 50

def normalize_phone_ir(s: str):
    digits = re.sub(r"[^\d+]", "", s or "")
    if digits.startswith("0098"):
        digits = "+98" + digits[4:]
    if digits.startswith("98") and not digits.startswith("+98"):
        digits = "+98" + digits[2:]
    if IR_MOBILE.match(digits):
        if digits.startswith("09"): return "+98" + digits[1:]
        return digits if digits.startswith("+") else "+" + digits
    if IR_LANDLINE.match(digits):
        if digits.startswith("0"): return "+98" + digits[1:]
        return digits if digits.startswith("+") else "+" + digits
    return None

def extract_contacts_from_html(html: str):
    emails = list(dict.fromkeys(EMAIL_RE.findall(html)))
    phones_raw = []
    for m in re.findall(r"tel:([+\d][+\d()\-\s]{5,})", html, flags=re.I):
        phones_raw.append(m)
    for m in re.findall(r"(?:(?<!\d)(?:\+?98|0)\d[\d\-\s()]{7,}\d)", html):
        phones_raw.append(m)
    phones = []
    for p in phones_raw:
        np = normalize_phone_ir(p)
        if np and np not in phones:
            phones.append(np)
    whats = None
    if ("wa.me" in html) or ("whatsapp" in html.lower()) or ("واتساپ" in html):
        whats = next(iter(phones), None)
    return {
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None,
        "whatsapp": whats
    }

def find_contact_links(base_url, soup: BeautifulSoup):
    keys = ["contact","تماس","درباره","ارتباط","تماس با ما","ارتباط با ما","contact-us","about"]
    found = []
    for a in soup.find_all("a", href=True):
        text = (a.get_text(" ", strip=True) or "").lower()
        href = a["href"].lower()
        if any(k in text for k in keys) or any(k in href for k in keys):
            url = absolute(base_url, a["href"])
            if is_allowed_url(url): found.append(url)
    uniq = []
    for u in found:
        if u not in uniq: uniq.append(u)
    return uniq[:6]

def guess_company_name(soup: BeautifulSoup):
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True): return h1.get_text(strip=True)[:120]
    og = soup.find("meta", attrs={"property":"og:site_name"})
    if og and og.get("content"): return og["content"][:120]
    if soup.title and soup.title.get_text(strip=True): return soup.title.get_text(strip=True)[:120]
    return ""

def scrape_site(url: str):
    out = {"name":"", "country":"ایران", "products":[], "contacts":{}, "source":url, "note":""}
    try:
        html = fetch_soft(url, timeout=30)
    except Exception as e:
        out["note"] = f"بارگذاری نشد: {e}"
        return out

    if REQUIRE_PERSIAN and not is_persian_enough(html):
        out["note"] = "صفحه فارسی نبود/کم‌متن فارسی داشت"
        return out

    soup = BeautifulSoup(html, "lxml")
    out["name"] = guess_company_name(soup)
    out["contacts"] = extract_contacts_from_html(html)

    for p in find_contact_links(url, soup):
        try:
            h = fetch_soft(p, timeout=20)
            c = extract_contacts_from_html(h)
            for k, v in c.items():
                if v and not out["contacts"].get(k):
                    out["contacts"][k] = v
        except Exception:
            continue

    meta = soup.find("meta", attrs={"name":"description"})
    if meta and meta.get("content"):
        out["products"] = [meta["content"][:200]]
    return out

# ===== موتورهای جستجو (بدون API) =====
def google_search(query: str, want=30):
    params = {"q": query, "hl": "fa", "gl": "ir", "num": 20, "udm": "14", "tbs": "li:1"}
    html = fetch_html("https://www.google.com/search", params=params)
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href.startswith("http"): continue
        if not is_allowed_url(href): continue
        txt = (a.get_text(" ", strip=True) or "")
        if txt and len(txt) < 2: continue
        out.append({"title": txt[:120] or href, "url": href})
        if len(out) >= want: break
    if not out:
        for g in soup.select("div.g a[href]"):
            href = g.get("href", "")
            if href.startswith("http") and is_allowed_url(href):
                t = g.get_text(" ", strip=True)
                out.append({"title": t[:120] or href, "url": href})
                if len(out) >= want: break
    return out

def ddg_search(query: str, want=30):
    q = urllib.parse.quote_plus(query)
    html = fetch_html(f"https://duckduckgo.com/html/?q={q}")
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select(".result__a"):
        href = a.get("href")
        if not (href and href.startswith("http") and is_allowed_url(href)):
            continue
        title = a.get_text(" ", strip=True)
        out.append({"title": title[:120] or href, "url": href})
        if len(out) >= want: break
    return out

def multi_search(query: str):
    for engine in (google_search, ddg_search):
        try:
            links = engine(query, want=60)
            if links: return links
        except Exception:
            continue
    return []

def dedup_urls(items, limit, exclude:set):
    seen, out = set(), []
    for it in items:
        u = it["url"].split("#")[0]
        if u in exclude:        # حذف مواردی که کاربر گفت قبلاً دیده
            continue
        if u in seen:
            continue
        seen.add(u); out.append(it)
        if len(out) >= limit:
            break
    return out

# ===== ساخت کوئری‌های ایران-محور =====
def build_queries(q: str):
    base = [
        f"{q} کارخانه site:.ir تماس",
        f"{q} تولیدکننده site:.ir تماس ایمیل",
        f"{q} تامین کننده site:.ir ارتباط با ما",
        f"{q} شرکت {q} site:.ir تماس",
        f"{q} عمده site:.ir تماس",
        f"{q} کنسانتره site:.ir تماس",
        f"{q} supplier site:.ir contact email"
    ]
    # تنوع شهر/استان برای لینک‌های بیشتر
    cities = ["تهران","اصفهان","مشهد","شیراز","تبریز","کرج","قم","اهواز","سمنان","یزد","کرمان"]
    base += [f"{q} کارخانه {c} site:.ir تماس" for c in cities[:6]]
    return base

# ===== نقطهٔ ورود اصلی =====
def find_suppliers(query: str, limit: int = 30, exclude: set = None):
    exclude = exclude or set()
    pool = []
    for q in build_queries(query.strip()):
        try:
            pool += multi_search(q)
        except Exception:
            continue

    # ددآپ + حذف موارد قبلی کاربر + فقط .ir (قبلاً is_allowed_url انجام می‌دهد)
    links = dedup_urls([it for it in pool if is_allowed_url(it["url"])],
                       limit=limit*3, exclude=exclude)

    if not links:
        return []

    results = []
    for s in links[:limit]:
        try:
            item = scrape_site(s["url"])
            if not item["name"]:
                item["name"] = s.get("title") or s["url"]
            results.append(item)
        except Exception as e:
            results.append({
                "name": s.get("title") or s.get("url"),
                "country": "ایران", "products": [], "contacts": {},
                "source": s["url"], "note": f"خطا در اسکن: {e}"
            })

    # اولویت به نتایج دارای تماس
    def has_contact(x):
        c = x.get("contacts") or {}
        return bool(c.get("email") or c.get("phone") or c.get("whatsapp"))
    results.sort(key=lambda x: (not has_contact(x), x.get("name") or ""))

    return results

# ===== گزارش دیباگ =====
def debug_collect(query: str, limit: int = 30, exclude: set = None):
    exclude = exclude or set()
    tries = []
    pool = []
    for q in build_queries(query.strip()):
        try:
            lst = multi_search(q)
            tries.append({"q": q, "count": len(lst)})
            pool += lst
        except Exception as e:
            tries.append({"q": q, "error": str(e)})
    picked = dedup_urls([it for it in pool if is_allowed_url(it["url"])],
                        limit=limit*3, exclude=exclude)
    return {"query": query, "tries": tries, "picked": picked[:limit]}
