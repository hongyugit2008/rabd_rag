import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

load_dotenv()

# 建议把 API Key 放在 .env 文件里，不要硬编码
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "")

def deepseek_llm():
    """
    创建并返回 DeepSeek LLM 实例

    Returns:
        ChatOpenAI: 配置好的 DeepSeek 聊天模型实例
    """
    if not DEEPSEEK_API_KEY:
        raise ValueError(
            "DeepSeek API Key 未配置！\n"
            "请在 .env 文件中设置 DEEPSEEK_API_KEY=your-api-key"
        )
    base_url = DEEPSEEK_BASE_URL.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    llm = ChatOpenAI(
        model=DEEPSEEK_MODEL,
        openai_api_key=DEEPSEEK_API_KEY,
        openai_api_base=base_url,
        temperature=0.7,
        max_tokens=2048,
    )
    return llm

# 建议把 API Key 放在 .env 文件里，不要硬编码
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")

def ollama_llm():
    """
    创建并返回 Ollama LLM 实例（支持工具调用）

    Returns:
        ChatOllama: 配置好的 Ollama 聊天模型实例

    Note:
        使用前请确保：
        1. 已安装 Ollama: https://ollama.ai/
        2. Ollama 服务正在运行
        3. 已拉取所需模型，例如: ollama pull llama3.2:3b

        推荐使用支持工具调用的模型：
        - qwen2.5:7b (推荐)
        - llama3.2:3b
        - mistral:7b
    """
    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.7,
        num_predict=2048,
    )
    return llm