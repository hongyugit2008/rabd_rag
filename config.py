# 全局基础配置
import os
from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else default


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


# 服务配置
HOST = _get_env("HOST", "127.0.0.1")
PORT = _get_env_int("PORT", 8000)

# MySQL数据库配置
MYSQL_HOST = _get_env("MYSQL_HOST", "127.0.0.1")
MYSQL_USER = _get_env("MYSQL_USER", "root")
MYSQL_PASSWORD = _get_env("MYSQL_PASSWORD", "1234567")
MYSQL_DB = _get_env("MYSQL_DB", "rag_rbac")
MYSQL_PORT = _get_env_int("MYSQL_PORT", 3306)

# 向量库配置（轻量化Chroma）
CHROMA_PERSIST_PATH = _get_env("CHROMA_PERSIST_PATH", "./chroma_db")

# Embedding 模型配置
EMBEDDING_MODEL = _get_env("EMBEDDING_MODEL", "./models/bge-small-zh-v1.5")

# 大模型配置
LLM_API_KEY = _get_env("LLM_API_KEY", "")
LLM_BASE_URL = _get_env("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODE = _get_env("LLM_MODE", "deepseek-chat")

# 权限常量定义
ROLE_LEVEL_MAP = {
    0: "普通员工",
    1: "业务骨干",
    2: "部门负责人",
    3: "高管/管理员"
}

# 角色允许访问的最大文档密级
ROLE_SECRET_RULE = {
    0: 1,
    1: 2,
    2: 3,
    3: 3
}
