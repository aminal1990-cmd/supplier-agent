# agent_logic.py — Supplier Agent (ایران‌محور + fallback) با engine قابل انتخاب
import re, time, random, urllib.parse
import requests
from bs4 import BeautifulSoup

# ===== تنظیمات =====
PAUSE = (0.45, 1.1)  # مکث مودبانه
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
]
BLOCKED = ("google.","webcache.google","maps.google","translate.google","accounts.google",
           "duckduckgo.","qwant.","bing.","yahoo.","facebook.","twitter.","linkedin.",
           "instagram.","youtube.","t.me/","telegram.")

PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")
EMAIL_RE   = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I)
IR_MOBILE  = re.compile(r"^(?:\+?98|0)?9\d{9}$")
IR_FIX     = re.compile(r"^(?:\+?98|0)\d{9,10}$")

def H():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache", "Pragma": "no-cache",
    }

def nap(): time.sleep(random.uniform(*PAUSE))

def fetch(url, params=None, timeout=25):
    r = requests.get(url, params=params or {}, headers=H(), timeout=timeout)
    r.raise_for_status(); return r.text

def fetch_soft(url, timeout=25): nap(); return fetch(url, timeout=timeout)

def host(url):
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "").lower()

def is_allowed(u, only_ir=False):
    h = host(u)
    if not h: return False
    if any(b in h for b in BLOCKED): return False
    if only_ir and not h.endswith(".ir"): return False
    return True

def is_persian(html): return len(PERSIAN_RE.findall(html)) >= 40

def absolute(base, href): return urllib.parse.urljoin(base, href)

def normalize_phone_ir(s):
    digits = re.sub(r"[^\d+]", "", s or "")
    if digits.startswith("0098"): digits = "+98" + digits[4:]
    if digits.startswith("98") and not digits.startswith("+98"): digits = "+98" + digits[2:]
    if IR_MOBILE.match(digits):
        if digits.startswith("09"): return "+98" + digits[1:]
        return digits if digits.startswith("+") else "+" + digits
    if IR_FIX.match(digits):
        if digits.startswith("0"): return "+98" + digits[1:]
        return digits if digits.startswith("+") else "+" + digits
    return None

def extract_contacts(html):
    emails = list(dict.fromkeys(EMAIL_RE.findall(html)))
    phones_raw = []
    phones_raw += re.findall(r"tel:([+\d][+\d()\-\s]{5,})", html, flags=re.I)
    phones_raw += re.findall(r"(?:(?<!\d)(?:\+?98|0)\d[\d\-\s()]{7,}\d)", html)
    phones = []
    for p in phones_raw:
        np = normalize_phone_ir(p)
        if np and np not in phones: phones.append(np)
    whats = None
    if ("wa.me" in html) or ("whatsapp" in html.lower()) or ("واتساپ" in html):
        whats = next(iter(phones), None)
    return {"email": (emails[0] if emails else None), "phone": (phones[0] if phones else None), "whatsapp": whats}

def contact_links(base, soup):
    keys = ["contact","تماس","درباره","ارتباط","تماس با ما","ارتباط با ما","contact-us","about"]
    out = []
    for a in soup.find_all("a", href=True):
        txt = (a.get_text(" ", strip=True) or "").lower(); href = a["href"].lower()
        if any(k in txt for k in keys) or any(k in href for k in keys):
            out.append(absolute(base, a["href"]))
    uniq = []; [uniq.append(u) for u in out if u not in uniq]
    return uniq[:6]

def guess_name(soup):
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True): return h1.get_text(strip=True)[:120]
    og = soup.find("meta", attrs={"property":"og:site_name"})
    if og and og.get("content"): return og["content"][:120]
    if soup.title and soup.title.get_text(strip=True): return soup.title.get_text(strip=True)[:120]
    return ""

def scrape_site(url, require_persian=False):
    out = {"name":"", "country":None, "products":[], "contacts":{}, "source":url, "note":""}
    try:
        html = fetch_soft(url, timeout=30)
    except Exception as e:
        out["note"] = f"بارگذاری نشد: {e}"; return out
    if require_persian and not is_persian(html):
        out["note"] = "صفحه فارسی نبود/کم‌متن فارسی داشت"; return out
    soup = BeautifulSoup(html, "lxml")
    out["name"] = guess_name(soup)
    out["contacts"] = extract_contacts(html)
    for p in contact_links(url, soup):
        try:
            h = fetch_soft(p, timeout=20); c = extract_contacts(h)
            for k, v in c.items():
                if v and not out["contacts"].get(k):
                    out["contacts"][k] = v
        except Exception: continue
    meta = soup.find("meta", attrs={"name":"description"})
    if meta and meta.get("content"): out["products"] = [meta["content"][:200]]
    return out

# ===== موتورهای جست‌وجو (HTML) =====
def google_search(q, want=40, only_ir=True):
    params = {"q": q, "hl":"fa", "gl":"ir", "num":20, "udm":"14", "tbs":"li:1"}
    html = fetch("https://www.google.com/search", params=params)
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href^='http']"):
        href = a.get("href","")
        if not is_allowed(href, only_ir): continue
        t = (a.get_text(" ", strip=True) or "").strip()
        if not t: continue
        out.append({"title": t[:120], "url": href})
        if len(out) >= want: break
    if not out:
        for g in soup.select("div.g a[href^='http']"):
            href = g.get("href","")
            if is_allowed(href, only_ir):
                t = g.get_text(" ", strip=True)
                out.append({"title": t[:120] or href, "url": href})
                if len(out) >= want: break
    return out

def startpage_search(query: str, want=40, only_ir=True):
    q = urllib.parse.quote_plus(query)
    html = fetch(f"https://www.startpage.com/sp/search?query={q}&language=fa")
    soup = BeautifulSoup(html, "lxml")
    out = []
    # نتایج اصلی استارت‌پیج
    for r in soup.select(".w-gl__result"):
        a = r.select_one("a.w-gl__result-title")
        if not a: 
            a = r.select_one("a[href^='http']")  # fallback
        if not a: 
            continue
        href = a.get("href")
        if not href or not href.startswith("http"):
            continue
        if not is_allowed(href, only_ir):
            continue
        title = a.get_text(" ", strip=True) or href
        out.append({"title": title[:120], "url": href})
        if len(out) >= want:
            break
    return out

def ddg_search(q, want=40, only_ir=True):
    qq = urllib.parse.quote_plus(q)
    html = fetch(f"https://duckduckgo.com/html/?q={qq}")
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select(".result__a"):
        href = a.get("href")
        if not (href and href.startswith("http") and is_allowed(href, only_ir)): continue
        t = a.get_text(" ", strip=True)
        out.append({"title": t[:120] or href, "url": href})
        if len(out) >= want: break
    return out

def multi_search(q, only_ir=True, engine_order=("google","startpage","ddg")):
    for name in engine_order:
        try:
            if name == "google":
                links = google_search(q, want=40, only_ir=only_ir)
            elif name == "startpage":
                links = startpage_search(q, want=40, only_ir=only_ir)
            elif name == "ddg":
                links = ddg_search(q, want=40, only_ir=only_ir)
            else:
                continue
            if links:
                return links
        except Exception:
            continue
    return []

def dedup(items, limit, exclude:set):
    seen, out = set(), []
    for it in items:
        u = it["url"].split("#")[0]
        if u in exclude: continue
        if u in seen: continue
        seen.add(u); out.append(it)
        if len(out) >= limit: break
    return out

# ===== کوئری‌ساز =====
def build_queries(q, only_ir=True):
    tag = "site:.ir " if only_ir else ""
    base = [
        f"{q} کارخانه {tag}تماس",
        f"{q} تولیدکننده {tag}تماس ایمیل",
        f"{q} تامین کننده {tag}ارتباط با ما",
        f"{q} شرکت {q} {tag}تماس",
        f"{q} عمده {tag}تماس",
        f"{q} supplier {tag}contact email",
    ]
    cities = ["تهران","اصفهان","مشهد","شیراز","تبریز","کرج"]
    base += [f"{q} کارخانه {c} {tag}تماس" for c in cities]
    return base

# ===== نقطهٔ ورود اصلی =====
def find_suppliers(query: str, limit: int = 30, exclude: set = None, engine_order=("google","startpage","ddg")):
    exclude = exclude or set()
    # مرحله A: سفت — فقط .ir و صفحه فارسی
    pool = []
    for qq in build_queries(query.strip(), only_ir=True):
        try: pool += multi_search(qq, only_ir=True, engine_order=engine_order)
        except Exception: continue
    links = dedup(pool, limit=limit*3, exclude=exclude)

    results = []
    def scan(urls, require_persian):
        out = []
        for s in urls[:limit]:
            try:
                it = scrape_site(s["url"], require_persian=require_persian)
                if not it["name"]: it["name"] = s.get("title") or s["url"]
                out.append(it)
            except Exception as e:
                out.append({"name": s.get("title") or s.get("url"),
                            "country": None, "products": [], "contacts": {},
                            "source": s["url"], "note": f"خطا در اسکن: {e}"})
        return out

    if links:
        results = scan(links, require_persian=True)

    # مرحله B: fallback — دامنه آزاد و بدون الزام فارسی (برای پر شدن نتایج)
    if len(results) < limit:
        pool2 = []
        for qq in build_queries(query.strip(), only_ir=False):
            try: pool2 += multi_search(qq, only_ir=False, engine_order=engine_order)
            except Exception: continue
        seen_urls = exclude.union({r["source"] for r in results if r.get("source")})
        links2 = dedup(pool2, limit=limit*4, exclude=seen_urls)
        results += scan(links2, require_persian=False)

    # مرتب‌سازی:‌ اولویت با داشتن راه تماس
    def has_contact(x):
        c = x.get("contacts") or {}
        return bool(c.get("email") or c.get("phone") or c.get("whatsapp"))
    results = results[:limit*2]
    results.sort(key=lambda x: (not has_contact(x), x.get("name") or ""))

    return results[:limit]

# ===== گزارش برای /debug =====
def debug_collect(query: str, limit: int = 30, exclude: set = None, engine_order=("google","startpage","ddg")):
    exclude = exclude or set()
    rep = {"query": query, "tries": [], "picked": []}
    pool = []
    for qq in build_queries(query.strip(), only_ir=True):
        try:
            lst = multi_search(qq, only_ir=True, engine_order=engine_order)
            rep["tries"].append({"q": qq, "count": len(lst)})
            pool += lst
        except Exception as e:
            rep["tries"].append({"q": qq, "error": str(e)})
    picked = dedup(pool, limit=limit*3, exclude=exclude)
    if len(picked) < limit:
        pool2 = []
        for qq in build_queries(query.strip(), only_ir=False):
            try:
                lst = multi_search(qq, only_ir=False, engine_order=engine_order)
                rep["tries"].append({"q": qq, "count": len(lst)})
                pool2 += lst
            except Exception as e:
                rep["tries"].append({"q": qq, "error": str(e)})
        picked2 = dedup(pool2, limit=limit*4, exclude=exclude.union({p["url"] for p in picked}))
        picked += picked2
    rep["picked"] = picked[:limit]
    return rep
