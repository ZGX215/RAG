"""演示新的入库 API：在提交任务时指定 classification。"""
import sys
sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

import requests
import time

BASE = "http://localhost:8000"

print("=" * 60)
print("演示：通过 API 入库指定密级文档")
print("=" * 60)

# 先做健康检查
try:
    r = requests.get(f"{BASE}/health")
    print(f"Health: {r.json()}")
except Exception as e:
    print(f"Health check failed: {e}")
    print("请确保服务已启动: python main.py")
    sys.exit(1)

# 演示：分别入库三个不同密级文档
test_files = [
    ("E:/trae/cede/mcu-rag-qa-v2/data/test_permission_public.txt", "公开信息", "public"),
    ("E:/trae/cede/mcu-rag-qa-v2/data/test_permission_internal.txt", "内部信息", "internal"),
    ("E:/trae/cede/mcu-rag-qa-v2/data/test_permission_confidential.txt", "机密信息", "confidential"),
]

task_ids = []

for file_path, doc_name, classification in test_files:
    print(f"\n提交入库: {doc_name} ({classification})")
    headers = {"Content-Type": "application/json"}
    payload = {
        "file_path": file_path,
        "doc_name": doc_name,
        "classification": classification,
    }
    r = requests.post(f"{BASE}/api/v1/ingest", headers=headers, json=payload)
    data = r.json()
    print(f"  task_id: {data.get('task_id')}, status: {data.get('status')}")
    task_ids.append((data.get('task_id'), doc_name, classification))

# 等待任务完成
print("\n等待入库任务完成...")
for task_id, doc_name, classification in task_ids:
    if not task_id:
        continue
    for _ in range(20):
        r = requests.get(f"{BASE}/api/v1/ingest/{task_id}")
        data = r.json()
        if data.get('status') in ['success', 'done']:
            break
        if data.get('status') == 'pending':
            time.sleep(2)
            continue
        if data.get('status') == 'failed':
            print(f"  {doc_name} 入库失败: {data.get('result')}")
            break
    print(f"  {doc_name} ({classification}): {data.get('status')}, result={data.get('result')}")

# 查询健康，看总数
r = requests.get(f"{BASE}/health")
print(f"\n入库完成后文档总数: {r.json()}")

print("\n" + "=" * 60)
print("现在可以通过设置 X-User-Clearance 请求头测试权限过滤")
print("例如:")
print('  X-User-Clearance: public      → 只能看到 public 文档')
print('  X-User-Clearance: internal    → 只能看到 public + internal 文档')
print('  X-User-Clearance: confidential → 可以看到所有文档')
print("=" * 60)
