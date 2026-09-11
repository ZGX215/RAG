"""初始化测试账号（幂等：已存在则更新密级与密码）。

四级密级各建一个账号，用于验证权限过滤：

    用户名        密码          密级            可见范围
    guest         guest123      public          仅公开文档
    engineer      eng123        internal        + 内部文档
    finance       fin123        confidential    + 机密文档（财务/薪资）
    admin         admin123      secret          全部（含绝密大客户名单）

用法::

    python scripts/init_users.py              # 创建/更新
    python scripts/init_users.py --reset      # 先清空 users 表再创建
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import crud  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import User  # noqa: E402

ACCOUNTS = [
    # username,   password,    clearance,       display_name,   dept
    ("guest",    "guest123",  "public",       "访客",         "guest"),
    ("engineer", "eng123",    "internal",     "研发工程师",   "tech"),
    ("finance",  "fin123",    "confidential", "财务人员",     "finance"),
    ("admin",    "admin123",  "secret",       "系统管理员",   "admin"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="初始化测试账号")
    ap.add_argument("--reset", action="store_true", help="先清空 users 表")
    args = ap.parse_args()

    init_db()  # 确保表已建立（含新增的 users 表）

    db = SessionLocal()
    try:
        if args.reset:
            n = db.query(User).delete()
            db.commit()
            print(f"[reset] 已清空 users 表（{n} 条）")

        for username, pwd, clearance, disp, dept in ACCOUNTS:
            u = crud.get_user_by_username(db, username)
            if u:
                # 已存在：更新密级/部门/口令，保证脚本可重复执行
                from app.auth.service import hash_password, new_salt
                u.salt = new_salt()
                u.password_hash = hash_password(pwd, u.salt)
                u.clearance = clearance
                u.display_name = disp
                u.dept = dept
                u.is_active = True
                db.commit()
                print(f"[update] {username:<9} clearance={clearance}")
            else:
                crud.create_user(
                    db, username=username, password=pwd,
                    clearance=clearance, display_name=disp, dept=dept,
                )
                print(f"[create] {username:<9} clearance={clearance}")

        total = crud.count_users(db)
        print(f"\n完成，当前用户总数：{total}\n")
        print(f"{'用户名':<11}{'密码':<12}{'密级':<15}可见文档")
        print("-" * 58)
        visible = {
            "public": "公开",
            "internal": "公开 + 内部",
            "confidential": "公开 + 内部 + 机密",
            "secret": "全部（含绝密）",
        }
        for username, pwd, clearance, _d, _t in ACCOUNTS:
            print(f"{username:<11}{pwd:<12}{clearance:<15}{visible[clearance]}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
