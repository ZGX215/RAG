"""本地测试批量入库（不用 HTTP API，直接执行）。"""
import sys
sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

from app.ingest.name_classifier import validate_batch_files

DATA_DIR = "E:/trae/cede/mcu-rag-qa-v2/data/batch_test"

print("=" * 70)
print("测试 1：文件名校验 + 批量拒绝")
print("=" * 70)

# 混合合格 + 不合格
file_paths = [
    f"{DATA_DIR}/公司简介_PUBLIC.txt",
    f"{DATA_DIR}/组织架构_INTERNAL.txt",
    f"{DATA_DIR}/财务数据_CONFIDENTIAL.txt",
    f"{DATA_DIR}/错误格式没有后缀.txt",
]

results = validate_batch_files(file_paths)

total = len(results)
passed = [r for r in results if r.is_valid]
rejected = [r for r in results if not r.is_valid]

print(f"总数: {total}, 通过: {len(passed)}, 拒绝: {len(rejected)}")
for r in rejected:
    print(f"  ❌ {r.file_path}: {r.error}")

if rejected:
    print("\n✅ 按照规则，发现不合格文件 → 整批拒绝，不入库")
else:
    print("\n❌ 预期应该有不合格文件被拒绝")

print("\n" + "=" * 70)
print("测试 2：全部合格 → 全部通过")
print("=" * 70)

file_paths = [
    f"{DATA_DIR}/公司简介_PUBLIC.txt",
    f"{DATA_DIR}/组织架构_INTERNAL.txt",
    f"{DATA_DIR}/财务数据_CONFIDENTIAL.txt",
]

results = validate_batch_files(file_paths)
total = len(results)
passed = [r for r in results if r.is_valid]
rejected = [r for r in results if not r.is_valid]

print(f"总数: {total}, 通过: {len(passed)}, 拒绝: {len(rejected)}")

for r in passed:
    print(f"  ✅ {r.clean_name} → {r.classification.value}")

if len(passed) == 3 and not rejected:
    print("\n✅ 全部通过，符合要求")
else:
    print("\n❌ 不合格")

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)
