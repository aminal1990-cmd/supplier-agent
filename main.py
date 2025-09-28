from flask import Flask, request, jsonify
from flask_cors import CORS
from agent_logic import find_suppliers  # مهم: فایل در ریشهٔ ریپو باشد

app = Flask(__name__)
CORS(app)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/search")
def search():
    data = request.get_json(force=True, silent=True) or {}
    q = (data.get("query") or data.get("q") or "").strip()
    if not q:
        return jsonify({"error": "empty query"}), 400
    try:
        results = find_suppliers(q)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
