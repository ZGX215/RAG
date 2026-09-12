import json

import requests

BASE = 'http://localhost:8000'
DATA_DIR = 'E:/trae/cede/mcu-rag-qa-v2/data/batch_test'

print("=== 测试 1：全部合格文件 ===")
files = [
    f'{DATA_DIR}/公司简介_PUBLIC.txt',
    f'{DATA_DIR}/组织架构_INTERNAL.txt',
    f'{DATA_DIR}/财务数据_CONFIDENTIAL.txt',
]
r = requests.post(
    f'{BASE}/api/v1/ingest/by-name',
    headers={'Content-Type': 'application/json'},
    json={'file_paths': files},
)
print(f'Status Code: {r.status_code}')
data = r.json()
print(json.dumps(data, indent=2, ensure_ascii=False))
