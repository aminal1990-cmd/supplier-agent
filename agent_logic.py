# agent_logic.py
# ⬇️ فعلاً یک نمونه ساده که بر اساس متن جستجو خروجی می‌دهد.
# بعداً همین تابع را با منطق واقعیِ خودت جایگزین می‌کنیم.

def find_suppliers(query: str):
    # ساختار خروجی باید «لیست»ی از «دیکشنری» باشد.
    # کلیدهای پیشنهادی: name, country, products (list), contacts (dict), source, note
    return [
        {
            "name": f"شرکت الف - مرتبط با: {query}",
            "country": "ایران",
            "products": [f"{query} بریکس 36-38"],
            "contacts": {"email": "a@example.com", "phone": "+98-21-111111"},
            "source": "https://site-a.example",
            "note": "سابقه صادرات"
        },
        {
            "name": f"شرکت ب - مرتبط با: {query}",
            "country": "ترکیه",
            "products": [f"{query} پریمیوم"],
            "contacts": {"email": "b@example.com"},
            "source": "https://site-b.example",
            "note": ""
        }
    ]
