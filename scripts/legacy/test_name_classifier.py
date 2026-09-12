"""测试文件名解析密级功能。"""
import sys

sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

from app.ingest.name_classifier import parse_classification_from_filename

test_cases = [
    # 合法文件名
    ("公司简介_PUBLIC.txt", True, "公司简介", "public"),
    ("内部纪要_INTERNAL.docx", True, "内部纪要", "internal"),
    ("核心财务_confidential.pdf", True, "核心财务", "confidential"),
    ("绝密文档_SECRET.md", True, "绝密文档", "secret"),
    ("A_B_C_PUBLIC.txt", True, "A_B_C", "public"),  # 多个下划线
    ("MixedCase_CONFIDENTIAL.PDF", True, "MixedCase", "confidential"),  # 大小写混合
    ("E:/data/财报_CONFIDENTIAL.pdf", True, "财报", "confidential"),  # 含路径

    # 不合法文件名
    ("公司简介.txt", False, "", ""),  # 缺少权限后缀
    ("_PUBLIC.txt", False, "", ""),  # 没有实际名称
    ("公司简介_UNKNOWN.txt", False, "", ""),  # 不支持的权限后缀
    ("公司简介_public_internal.txt", True, "公司简介_public", "internal"),  # 取最后一个后缀
]

print("=" * 70)
print("文件名解析密级 单元测试")
print("=" * 70)

all_pass = True
for file_path, expect_valid, expect_name, expect_cls in test_cases:
    result = parse_classification_from_filename(file_path)

    if result.is_valid != expect_valid:
        print(f"❌ [{file_path}] valid={result.is_valid} 期望={expect_valid} | {result.error}")
        all_pass = False
        continue

    if result.is_valid:
        name_ok = result.clean_name == expect_name
        cls_ok = result.classification.value == expect_cls
        if name_ok and cls_ok:
            print(f"✅ [{file_path}] → name={result.clean_name}, cls={result.classification.value}")
        else:
            print(f"❌ [{file_path}] name={result.clean_name}(期望{expect_name}), cls={result.classification.value}(期望{expect_cls})")
            all_pass = False
    else:
        print(f"✅ [{file_path}] 正确拒绝: {result.error}")

print()
if all_pass:
    print("🎉 所有单元测试通过!")
else:
    print("❌ 部分测试失败")
