import requests
import json

BASE_URL = "https://zarvio-backend.onrender.com"

endpoints_to_test = [
    {"method": "GET", "url": "/health"},
    {"method": "GET", "url": "/auth/me"},
    {"method": "GET", "url": "/prospects"},
    {"method": "GET", "url": "/api/metrics/overview"},
    {"method": "POST", "url": "/copilot", "json": {"messages": [{"role": "user", "content": "hi"}], "user_id": "test"}},
    {"method": "GET", "url": "/leads"},
    {"method": "GET", "url": "/api/deal-room/1"}, # Expect 404 (Lead not found)
    {"method": "GET", "url": "/api/ras/1"},       # Expect 404
]

results = []

for ep in endpoints_to_test:
    method = ep["method"]
    url = BASE_URL + ep["url"]
    
    try:
        if method == "GET":
            res = requests.get(url, timeout=10)
        else:
            res = requests.post(url, json=ep.get("json", {}), timeout=10)
            
        status = res.status_code
        success = status in [200, 401, 404]  # 401 (needs auth) or 404 (lead missing) means API route is alive!
        results.append({
            "endpoint": ep["url"],
            "status": status,
            "alive": success
        })
    except Exception as e:
        results.append({
            "endpoint": ep["url"],
            "status": str(e),
            "alive": False
        })

print(json.dumps(results, indent=2))
