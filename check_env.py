"""环境自检：确认依赖装齐、数据库可用。

用法（在项目根目录、激活 conda 环境后）：
    python check_env.py
"""

import sys


def main() -> int:
    print("=" * 56)
    print("Python:", sys.version.split()[0], "|", sys.executable)
    print("=" * 56)

    ok = True

    packages = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("sqlalchemy", "sqlalchemy"),
        ("pydantic", "pydantic"),
        ("pydantic_settings", "pydantic_settings"),
        ("langchain", "langchain"),
        ("langchain_openai", "langchain_openai"),
        ("langgraph", "langgraph"),
        ("tiktoken", "tiktoken"),
        ("rank_bm25", "rank_bm25"),
        ("numpy", "numpy"),
        ("pypdf", "pypdf"),
        ("docx", "python-docx"),
        ("httpx", "httpx"),
        ("tenacity", "tenacity"),
        ("multipart", "python-multipart"),
    ]

    for module_name, label in packages:
        try:
            module = __import__(module_name)
            version = getattr(module, "__version__", "?")
            print(f"  [OK]   {label:<18} {version}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  [FAIL] {label:<18} {exc}")

    print("-" * 56)

    # 数据库自检
    try:
        from app.config import settings
        from app.db import Base, engine
        import app.models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        from sqlalchemy import inspect

        tables = sorted(inspect(engine).get_table_names())
        print(f"  [OK]   数据库 {settings.database_url}")
        print(f"         已建表 {len(tables)} 张：{', '.join(tables)}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  [FAIL] 数据库初始化：{exc}")

    print("=" * 56)
    if ok:
        print("环境自检通过，可以启动服务：")
        print("    uvicorn app.main:app --reload --port 8000")
    else:
        print("有依赖缺失，请先执行：")
        print("    python -m pip install -r requirements.txt")
    print("=" * 56)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
