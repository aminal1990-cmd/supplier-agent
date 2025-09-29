from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import csv, io, re, sys, traceback, json
from agent_logic import find_suppliers, debug_collect

app = Flask(__name__)
CORS(app)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/search")
def search():
    data = request.get_json(force=True, silent=True) or {}
    q = (data.get("query") or "").strip()
    limit = int(data.get("limit") or 30)
    exclude = set(data.get("exclude") or [])
    engine = (data.get("engine") or "auto").strip().lower()

    if not q:
        return jsonify({"error": "empty query"}), 400

    if engine in ("google","startpage","ddg","ddg_lite"):
        engine_order = (engine,)
    else:
        engine_order = ("google","startpage","ddg_lite","ddg")

    try:
        results = find_suppliers(q, limit=limit, exclude=exclude, engine_order=engine_order)
        return jsonify({"results": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.get("/debug")
def debug():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 30)
    exclude = set(request.args.getlist("exclude") or [])
    engine = (request.args.get("engine") or "auto").strip().lower()

    if not q:
        return Response("Add ?q=... to URL", status=400)

    if engine in ("google","startpage","ddg","ddg_lite"):
        engine_order = (engine,)
    else:
        engine_order = ("google","startpage","ddg_lite","ddg")

    try:
        report = debug_collect(q, limit=limit, exclude=exclude, engine_order=engine_order)
        return Response(json.dumps(report, ensure_ascii=False, indent=2),
                        mimetype="application/json; charset=utf-8")
    except Exception as e:
        traceback.print_exc()
        return Response(str(e), status=500)

@app.get("/export.csv")
def export_csv():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 30)
    exclude = set(request.args.getlist("exclude") or [])
    engine = (request.args.get("engine") or "auto").strip().lower()

    if not q:
        return Response("q param required", status=400)

    if engine in ("google","startpage","ddg","ddg_lite"):
        engine_order = (engine,)
    else:
        engine_order = ("google","startpage","ddg_lite","ddg")

    results = find_suppliers(q, limit=limit, exclude=exclude, engine_order=engine_order)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name","country","products","email","phone","whatsapp","source","note"])
    for r in results:
        contacts = r.get("contacts") or {}
        products = r.get("products") or []
        w.writerow([
            r.get("name") or "",
            r.get("country") or "",
            " ; ".join(products),
            contacts.get("email") or "",
            contacts.get("phone") or "",
            contacts.get("whatsapp") or "",
            r.get("source") or "",
            r.get("note") or "",
        ])
    fname = re.sub(r"[^A-Za-z0-9_\-]+", "_", q)[:40] or "export"
    csv_bytes = buf.getvalue().encode("utf-8-sig")
    return Response(
        csv_bytes,
        headers={
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f'attachment; filename="suppliers_{fname}.csv"'
        },
        status=200
    )
import requests

@app.get("/probe")
def probe():
    targets = {
        "google": "https://www.google.com/search?q=test",
        "startpage": "https://www.startpage.com/sp/search?query=test",
        "ddg_lite": "https://lite.duckduckgo.com/lite/?q=test",
        "example": "https://example.com/",
    }
    out = {}
    for k, url in targets.items():
        try:
            r = requests.get(url, timeout=10)
            out[k] = {"ok": True, "status": r.status_code, "len": len(r.text)}
        except Exception as e:
            out[k] = {"ok": False, "error": str(e)}
    return out
    # === DEBUG: بررسی مستقیم موتور و سلکتورها ===
from urllib.parse import urlparse, parse_qs, unquote
import requests
from bs4 import BeautifulSoup

def _clean_startpage_href(href: str) -> str:
    try:
        p = urlparse(href)
        if "startpage.com" in (p.netloc or "") and p.path.startswith("/rd"):
            q = parse_qs(p.query)
            for key in ("url", "u", "uddg"):
                if key in q and q[key]:
                    return unquote(q[key][0])
    except Exception:
        pass
    return href

def _clean_ddg_href(href: str) -> str:
    try:
        p = urlparse(href)
        if (p.netloc or "").endswith("duckduckgo.com") and p.path.startswith("/l/"):
            q = parse_qs(p.query)
            if "uddg" in q and q["uddg"]:
                return unquote(q["uddg"][0])
    except Exception:
        pass
    return href

@app.get("/debug_engine")
def debug_engine():
    q = (request.args.get("q") or "").strip()
    engine = (request.args.get("engine") or "startpage").strip().lower()
    if not q:
        return jsonify({"error":"Add ?q=..."}), 400

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    }

    try:
        if engine == "startpage":
            base = "https://www.startpage.com"
            url = f"{base}/sp/search"
            r = requests.get(url, params={"query": q, "language": "fa"}, headers=headers, timeout=25)
            raw = r.text
            soup = BeautifulSoup(raw, "lxml")

            # سلکتورهای اصلی و فالبک
            sel_main = [".w-gl__result a.w-gl__result-title", ".w-gl__result a[href]"]
            sel_fallback = ["a[href]"]

            def norm(h):
                if not h: return ""
                if h.startswith("/"): h = base + h
                h = _clean_startpage_href(h)
                return h

            buckets = {}
            for sel in sel_main + sel_fallback:
                links = []
                for a in soup.select(sel):
                    href = norm(a.get("href"))
                    if not href.startswith("http"):
                        continue
                    title = (a.get_text(" ", strip=True) or href)[:160]
                    links.append({"title": title, "url": href})
                    if len(links) >= 20:
                        break
                buckets[sel] = links

            return jsonify({
                "engine": "startpage",
                "status": r.status_code,
                "html_len": len(raw),
                "counts": {k: len(v) for k,v in buckets.items()},
                "sample": (buckets.get(sel_main[0]) or buckets.get(sel_main[1]) or buckets.get(sel_fallback[0]) or [])[:10],
            })

        elif engine in ("ddg_lite", "ddg"):
            base = "https://duckduckgo.com"
            url = "https://lite.duckduckgo.com/lite/"
            r = requests.get(url, params={"q": q}, headers=headers, timeout=25)
            raw = r.text
            soup = BeautifulSoup(raw, "lxml")

            sel_main = ["a.result-link", "td.result-link a"]
            sel_fallback = ["a[href]"]

            def norm(h):
                if not h: return ""
                if h.startswith("/"): h = base + h
                h = _clean_ddg_href(h)
                return h

            buckets = {}
            for sel in sel_main + sel_fallback:
                links = []
                for a in soup.select(sel):
                    href = norm(a.get("href"))
                    if not href.startswith("http"):
                        continue
                    title = (a.get_text(" ", strip=True) or href)[:160]
                    links.append({"title": title, "url": href})
                    if len(links) >= 20:
                        break
                buckets[sel] = links

            return jsonify({
                "engine": "ddg_lite",
                "status": r.status_code,
                "html_len": len(raw),
                "counts": {k: len(v) for k,v in buckets.items()},
                "sample": (buckets.get(sel_main[0]) or buckets.get(sel_main[1]) or buckets.get(sel_fallback[0]) or [])[:10],
            })

        elif engine == "google":
            url = "https://www.google.com/search"
            r = requests.get(url, params={"q": q, "hl":"fa", "gl":"ir", "num":20}, headers=headers, timeout=25)
            raw = r.text
            soup = BeautifulSoup(raw, "lxml")

            buckets = {}
            sel = "a[href^='http']"
            links = []
            for a in soup.select(sel):
                href = a.get("href") or ""
                if not href.startswith("http"): continue
                title = (a.get_text(" ", strip=True) or href)[:160]
                links.append({"title": title, "url": href})
                if len(links) >= 20:
                    break
            buckets[sel] = links

            return jsonify({
                "engine": "google",
                "status": r.status_code,
                "html_len": len(raw),
                "counts": {sel: len(links)},
                "sample": links[:10],
            })

        else:
            return jsonify({"error":"unknown engine"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
