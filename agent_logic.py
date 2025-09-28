def find_suppliers(query: str):
    # این فقط نمونه است؛ بعداً کد واقعی جستجو/خزش را جایگزین کن
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
