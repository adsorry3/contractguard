"""应用配置：全部来自 .env，禁止在代码里硬编码密钥。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ===== 应用 =====
    app_name: str = "ContractGuard"
    debug: bool = True

    # ===== 数据库 =====
    # 阶段 0 用 SQLite；以后换 PostgreSQL / MySQL 只改 .env 里这一项
    database_url: str = "sqlite:///./contractguard.db"

    # ===== 文件上传 =====
    upload_dir: str = "./uploads"
    max_upload_mb: int = 20

    # ===== DeepSeek（阶段 2）=====
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ===== Embedding（阶段 5）=====
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # ===== Redis（阶段 3：任务进度 / 分布式锁 / 报告缓存）=====
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_key_prefix: str = "cg"
    task_ttl_seconds: int = 3600
    cache_ttl_seconds: int = 300

    # ===== Eureka 注册中心（服务发现，Java 侧靠它发现 AI-SERVICE）=====
    eureka_enabled: bool = True
    eureka_url: str = "http://localhost:8761"
    ai_service_port: int = 8000


settings = Settings()
