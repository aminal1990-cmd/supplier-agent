from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from agent_logic import find_suppliers, debug_collect
import csv, io, re, sys, traceback, json

app = Flask(__name__)
CORS(app)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/search")
def search():
    data = request.get_json(force=True, silent=True) or {}
    q = (data.get("query") or data.get("q") or "").strip()
    print(f"[SEARCH] q='{q}'", file=sys.stderr, flush=True)
    if not q:
        return jsonify({"error": "empty query"}), 400
    try:
        results = find_suppliers(q)
        print(f"[SEARCH] results={len(results)}", file=sys.stderr, flush=True)
        return jsonify({"results": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# گزارش مرحلهٔ جستجو (فقط لینک‌ها، بدون اسکن عمیق سایت‌ها)
@app.get("/debug")
def debug():
    q = (request.args.get("q") or "").strip()
    if not q:
        return Response("Add ?q=... to URL", status=400)
    try:
        report = debug_collect(q)
        return Response(json.dumps(report, ensure_ascii=False, indent=2),
                        mimetype="application/json; charset=utf-8")
    except Exception as e:
        traceback.print_exc()
        return Response(str(e), status=500)

# خروجی CSV
@app.get("/export.csv")
def export_csv():
    q = (request.args.get("q") or "").strip()
    if not q:
        return Response("q param required", status=400)
    results = find_suppliers(q)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
