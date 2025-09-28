from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # اجازه درخواست از هر دامنه (برای اتصال صفحه)

def run_supplier_agent(query: str):
    # فعلاً خروجی نمونه (بعداً منطق واقعی را جایگزین می‌کنیم)
    return [{
        "name": "تامین‌کننده نمونه رب گوجه",
        "country": "ایران",
        "products": ["رب گوجه 36-38 بریکس"],
        "contacts": {"email": "sales@example.com", "phone": "+98-21-123456"},
        "source": "https://example.com",
        "note": "نمونه تستی"
    }]

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/search")
def search():
    data = request.get_json(force=True, silent=True) or {}
    q = (data.get("query") or data.get("q") or "").strip()
    if not q:
        return jsonify({"error": "empty query"}), 400
    return jsonify({"results": run_supplier_agent(q)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
