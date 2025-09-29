from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import io, csv, re, json, traceback, requests
import agent_logic as al
from agent_logic import find_suppliers, debug_collect

app = Flask(__name__)
CORS(app)

# سلامت
@app.get("/health")
def health():
    return {"ok": True}

# جستجو
@app.post("/search")
def search():
    data = request.get_json(force=True, silent=True) or {}
    q = (data.get("query") or "").strip()
    limit = int(data.get("limit") or 30)
    engine = (data.get("engine") or "auto").strip().lower()
    if not q: return jsonify({"error":"empty query"}),400

    engine_order = ("startpage","ddg_lite","mojeek","google") if engine=="auto" else (engine,)
    try:
        results = find_suppliers(q, limit=limit, engine_order=engine_order)
        return jsonify({"results": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# دیباگ
@app.get("/debug")
def debug():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 30)
    engine = (request.args.get("engine") or "auto").strip().lower()
    engine_order = ("startpage","ddg_lite","mojeek","google") if engine=="auto" else (engine,)
    rep = debug_collect(q, limit=limit, engine_order=engine_order)
    return Response(json.dumps(rep, ensure_ascii=False, indent=2),
                    mimetype="application/json; charset=utf-8")

# خروجی CSV
@app.get("/export.csv")
def export_csv():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or 30)
    engine = (request.args.get("engine") or "auto").strip().lower()
    engine_order = ("startpage","ddg_lite","mojeek","google") if engine=="auto" else (engine,)
    results = find_suppliers(q, limit=limit, engine_order=engine_order)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name","email","phone","whatsapp","source","note"])
    for r in results:
        c = r.get("contacts") or {}
        w.writerow([r.get("name"),c.get("email"),c.get("phone"),c.get("whatsapp"),r.get("source"),r.get("note")])
    fname = re.sub(r"[^A-Za-z0-9]+","_",q)[:30] or "export"
    return Response(buf.getvalue().encode("utf-8-sig"),
        headers={"Content-Disposition":f'attachment; filename="{fname}.csv"'},
        mimetype="text/csv")

# تست اتصال بیرونی
@app.get("/probe")
def probe():
    targets = {
        "google":"https://www.google.com/search?q=test",
        "startpage":"https://www.startpage.com/sp/search?query=test",
        "ddg_lite":"https://lite.duckduckgo.com/lite/?q=test",
        "mojeek":"https://www.mojeek.com/search?q=test",
    }
    out={}
    for k,u in targets.items():
        try:
            r=requests.get(u,timeout=10)
            out[k]={"ok":True,"status":r.status_code,"len":len(r.text)}
        except Exception as e:
            out[k]={"ok":False,"error":str(e)}
    return out

if __name__=="__main__":
    app.run(host="0.0.0.0",port=8080)
