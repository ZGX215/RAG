"""测试 API 请求并打印完整响应。"""
import requests
import json

BASE = "http://localhost:8000"

# 健康检查
r = requests.get(f"{BASE}/health")
print(f"Health: {r.json()}")

# 测试不同权限
for clearance in ["public", "internal", "confidential"]:
    headers = {
        "Content-Type": "application/json",
        "X-User-Clearance": clearance,
    }
    payload = {"question": "公司官网是什么", "top_k": 5}
    r = requests.post(f"{BASE}/api/v1/qa", headers=headers, json=payload)
    data = r.json()
    print(f"\n=== {clearance} ===")
    print(f"  Status: {r.status_code}")
    answer = data.get("answer", "")
    print(f"  Answer: {answer[:100] if answer else 'N/A'}")
    sources = data.get("sources", [])
    print(f"  Sources: {len(sources)}")
    for s in sources:
        print(f"    doc_name={s['doc_name']} score={s['score']:.3f} heading={s['heading_number']}")