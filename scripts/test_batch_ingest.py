"""测试批量入库 API：按文件名解析密级。"""
import sys
sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

import requests
import time
import json

BASE = "http://localhost:8000"

# 先检查服务是否在运行
try:
    r = requests.get(f"{BASE}/health")
    print(f"服务状态: {r.json()}")
except Exception as e:
    print(f"服务未启动: {e}")
    print("请先执行: python main.py")
    sys.exit(1)

DATA_DIR = "E:/trae/cede/mcu-rag-qa-v2/data/batch_test"

print("\n" + "=" * 70)
print("测试 1：全部合格 → 校验通过，全部入库")
print("=" * 70)

valid_files = [
    f"{DATA_DIR}/公司简介_PUBLIC.txt",
    f"{DATA_DIR}/组织架构_INTERNAL.txt",
    f"{DATA_DIR}/财务数据_CONFIDENTIAL.txt",
]

r = requests.post(
    f"{BASE}/api/v1/ingest/by-name",
    headers={"Content-Type": "application/json"},
    json={"file_paths": valid_files},
)
data = r.json()
print(f"状态: {data['status']}")
print(f"总数: {data['total_files']}, 通过: {data['passed_files']}, 拒绝: {len(data['rejected_files'])}")

if data['status'] == 'all_passed':
    print(f"task_ids: {data['task_ids']}")
    # 等待所有任务完成
    print("\n等待入库完成...")
    for tid in data['task_ids']:
        for _ in range(30):
            r = requests.get(f"{BASE}/api/v1/ingest/{tid}")
            st = r.json()
            if st['status'] in ['success', 'done', 'failure']:
                result = st.get('result', {})
                print(f"  {tid}: {st['status']} | {result.get('doc_name', '')} x{result.get('upserted', 0)} chunks")
                break
            time.sleep(2)
else:
    print(f"❌ 预期全部通过，但状态为 {data['status']}")
    for item in data.get('rejected_files', []):
        print(f"  {item['file_path']}: {item['error']}")

print("\n" + "=" * 70)
print("测试 2：有不合格文件名 → 拒绝整批")
print("=" * 70)

mixed_files = [
    f"{DATA_DIR}/公司简介_PUBLIC.txt",
    f"{DATA_DIR}/错误格式没有后缀.txt",  # 这个文件名没有后缀
]

r = requests.post(
    f"{BASE}/api/v1/ingest/by-name",
    headers={"Content-Type": "application/json"},
    json={"file_paths": mixed_files},
)
data = r.json()
print(f"状态: {data['status']}")
print(f"总数: {data['total_files']}, 通过: {data['passed_files']}, 拒绝: {len(data['rejected_files'])}")

if data['status'] == 'rejected':
    print("✅ 正确拒绝整批入库!")
    for item in data['rejected_files']:
        print(f"  {item['file_path']}: {item['error']}")
else:
    print(f"❌ 预期拒绝，但状态为 {data['status']}")

print("\n" + "=" * 70)
print("测试 3：验证权限过滤仍然有效")
print("=" * 70)

# 用 PUBLIC 用户查询机密内容
r = requests.post(
    f"{BASE}/api/v1/qa",
    headers={"Content-Type": "application/json", "X-User-Clearance": "public"},
    json={"question": "营业收入是多少", "top_k": 5},
)
data = r.json()
sources = data.get('sources', [])
print(f"PUBLIC 用户查询财报: {len(sources)} sources")
# 检查是否泄露了机密数据
for s in sources:
    if "财务" in s['doc_name']:
        print(f"  ❌ 越权泄露: {s['doc_name']}")
        break
else:
    print(f"  ✅ 机密数据未泄露")

# 用 CONFIDENTIAL 用户查询财报
r = requests.post(
    f"{BASE}/api/v1/qa",
    headers={"Content-Type": "application/json", "X-User-Clearance": "confidential"},
    json={"question": "营业收入是多少", "top_k": 5},
)
data = r.json()
sources = data.get('sources', [])
print(f"CONFIDENTIAL 用户查询财报: {len(sources)} sources")
for s in sources:
    print(f"  [{s['doc_name']}] score={s['score']:.3f}")

print("\n" + "=" * 70)
print("🎉 测试完成")
print("=" * 70)