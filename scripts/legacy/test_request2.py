"""测试机密数据查询权限。"""
import requests

BASE = "http://localhost:8000"

test_cases = [
    ("融资金额是多少", "public"),
    ("融资金额是多少", "internal"),
    ("融资金额是多少", "confidential"),
    ("CEO年薪", "public"),
    ("CEO年薪", "internal"),
    ("CEO年薪", "confidential"),
    ("公司组织架构", "public"),
    ("公司组织架构", "internal"),
    ("公司组织架构", "confidential"),
]

for question, clearance in test_cases:
    headers = {
        "Content-Type": "application/json",
        "X-User-Clearance": clearance,
    }
    payload = {"question": question, "top_k": 5}
    r = requests.post(f"{BASE}/api/v1/qa", headers=headers, json=payload)
    data = r.json()
    sources = data.get("sources", [])
    
    # 收集密级分布
    doc_classifications = []
    for s in sources:
        if "公开" in s["doc_name"]:
            doc_classifications.append("public")
        elif "内部" in s["doc_name"]:
            doc_classifications.append("internal")
        elif "机密" in s["doc_name"]:
            doc_classifications.append("confidential")
        else:
            doc_classifications.append("unknown")
    
    # 检查越权
    clearance_order = {"public": 0, "internal": 1, "confidential": 2}
    user_level = clearance_order.get(clearance, 0)
    doc_level_map = {"public": 0, "internal": 1, "confidential": 2}
    unauthorized = [c for c in doc_classifications if doc_level_map.get(c, 0) > user_level]
    
    if unauthorized:
        print(f"❌ [{clearance}] {question}: {len(sources)} sources, 越权={unauthorized}")
    else:
        print(f"✅ [{clearance}] {question}: {len(sources)} sources, 密级={doc_classifications}")