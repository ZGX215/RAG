"""权限测试 API 端到端测试脚本。
通过 HTTP API 测试不同权限用户，验证是否只返回授权范围内的文档。
"""
import requests

BASE_URL = "http://localhost:8000/api/v1/qa"


def test_api_permission(query: str, clearance: str, top_k: int = 5):
    """测试 API 权限过滤。"""
    headers = {
        "Content-Type": "application/json",
        "X-User-Clearance": clearance,
    }
    payload = {
        "question": query,
        "top_k": top_k,
    }
    
    response = requests.post(BASE_URL, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    
    print(f"\n查询: [{query}] | 用户权限: {clearance}")
    print(f"  返回结果: {len(data['sources'])} 个来源")
    classifications = []
    for source in data['sources']:
        # 从 doc_name 中提取密级（我们测试文档名包含它）
        if "公开" in source['doc_name']:
            cls = "public"
        elif "内部" in source['doc_name']:
            cls = "internal"
        elif "机密" in source['doc_name']:
            cls = "confidential"
        else:
            cls = "unknown"
        classifications.append(cls)
        print(f"    - [{cls}] score={source['score']:.3f} | {source['content'][:40]}...")
    
    # 权限检查
    clearance_order = {
        "public": 0,
        "internal": 1,
        "confidential": 2,
    }
    user_level = clearance_order.get(clearance, 0)
    unauthorized_found = []
    
    # 定义分类对应的密级
    doc_level_map = {
        "public": 0,
        "internal": 1,
        "confidential": 2,
    }
    
    for cls in classifications:
        doc_level = doc_level_map.get(cls, 0)
        if doc_level > user_level:
            unauthorized_found.append(cls)
    
    if unauthorized_found:
        print(f"  ❌ 失败: 发现越权文档 {unauthorized_found}")
        return False
    else:
        print("  ✅ 通过: 所有返回文档均在用户权限范围内")
        return True


def main():
    print("=" * 60)
    print("权限 Pre-Filter API 端到端测试")
    print("=" * 60)
    
    test_cases = [
        # (查询内容, 用户权限, 预期结果)
        ("公司官网是什么", "public"),
        ("公司官网是什么", "internal"),
        ("公司官网是什么", "confidential"),
        ("公司有哪些部门", "public"),
        ("公司有哪些部门", "internal"),
        ("公司有哪些部门", "confidential"),
        ("CEO年薪是多少", "public"),
        ("CEO年薪是多少", "internal"),
        ("CEO年薪是多少", "confidential"),
    ]
    
    all_passed = True
    for query, clearance in test_cases:
        passed = test_api_permission(query, clearance)
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有 API 端到端测试通过！")
    else:
        print("❌ 部分测试失败，请检查权限实现。")
    print("=" * 60)


if __name__ == "__main__":
    main()