#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAG 系统诊断脚本
用法: python debug_rag.py
"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ========== 配置区（根据你的环境修改）==========
CHROMA_PERSIST_DIR = "./chroma_db"  # ChromaDB 持久化目录
EMBEDDING_MODEL_PATH = "./models/bge-small-zh-v1.5"  # 本地嵌入模型路径


# ============================================

def init_chroma():
    """初始化 ChromaDB 连接"""
    from langchain_chroma import Chroma
    from langchain_huggingface import HuggingFaceEmbeddings

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_PATH,
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

    vector_store = Chroma(
        persist_directory=CHROMA_PERSIST_DIR,
        embedding_function=embeddings
    )
    return vector_store


def inspect_ocr_content(vector_store, source_filter=None, limit=10):
    """
    查看已存入的文档内容
    """
    print("\n" + "=" * 60)
    print("步骤1: 查看 OCR 内容完整性")
    print("=" * 60)

    if source_filter:
        results = vector_store.get(where={"source": source_filter}, limit=limit)
    else:
        results = vector_store.get(limit=limit)

    if not results['ids']:
        print("❌ 未找到任何文档，请先上传图片")
        return

    print(f"共找到 {len(results['ids'])} 个文档片段")

    for i, (doc_id, text, meta) in enumerate(zip(
            results['ids'], results['documents'], results['metadatas']
    )):
        print(f"\n--- 片段 {i + 1} ---")
        print(f"ID: {doc_id}")
        print(f"来源: {meta.get('source', '未知')}")
        print(f"内容 (前200字): {text[:200]}...")

    # 检查是否包含目标关键词
    keyword = input("\n请输入要检查的关键词 (如 '人之初'，直接回车跳过): ").strip()
    if keyword:
        found = any(keyword in doc for doc in results['documents'])
        if found:
            print(f"✅ 关键词 '{keyword}' 在文档中存在，OCR 正常")
        else:
            print(f"❌ 关键词 '{keyword}' 不存在，请检查 OCR 或图片预处理")


def debug_retrieval(vector_store, query, k=10):
    """
    调试检索召回
    """
    print("\n" + "=" * 60)
    print("步骤2: 调试检索召回")
    print("=" * 60)
    print(f"用户问题: {query}")

    # 执行检索
    docs_with_scores = vector_store.similarity_search_with_score(query, k=k)

    print(f"检索到 {len(docs_with_scores)} 个相关片段\n")

    for i, (doc, score) in enumerate(docs_with_scores):
        print(f"--- Top {i + 1} (相似度: {score:.4f}) ---")
        print(f"来源: {doc.metadata.get('source', '未知')}")
        print(f"内容: {doc.page_content[:200]}...")
        print()

    # 判断是否包含目标内容
    keyword = "人之初"
    found = any(keyword in doc.page_content for doc, _ in docs_with_scores)
    if found:
        print(f"✅ 检索结果中包含 '{keyword}'，问题可能在模型生成阶段")
    else:
        print(f"❌ 检索结果中未包含 '{keyword}'，问题在检索阶段")
        print("   建议: 调低相似度阈值，或增加 Top K，或优化文本分割策略")


def direct_model_test(query, chunk_text):
    """
    直接测试大模型能力（绕过检索）
    """
    print("\n" + "=" * 60)
    print("步骤3: 测试大模型能力（绕过检索）")
    print("=" * 60)

    # 这里假设你已经配置了 DeepSeek API
    from openai import OpenAI

    client = OpenAI(
        base_url="https://api.deepseek.com/v1",  # 替换为你的 API 地址
        api_key="your-api-key"  # 替换为你的 API Key
    )

    prompt = f"""请根据以下文档片段回答问题。

文档片段：
{chunk_text}

问题：{query}

请直接给出答案，不要解释。"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        answer = response.choices[0].message.content
        print(f"模型答案: {answer}")
        print("\n如果答案正确，说明问题在检索召回；如果答案错误，说明模型能力不足")
    except Exception as e:
        print(f"调用模型失败: {e}")


def main():
    print("RAG 系统诊断工具")
    print("=" * 60)

    # 初始化
    vector_store = init_chroma()

    # 步骤1: 查看OCR内容
    inspect_ocr_content(vector_store)

    # 步骤2: 调试检索
    query = input("\n请输入测试问题 (如 '人之初，性本善的下一句是什么？'): ").strip()
    if query:
        debug_retrieval(vector_store, query)

    # 步骤3: 如果检索到了相关片段，测试模型
    docs = vector_store.similarity_search(query, k=1)
    if docs:
        print("\n是否进行模型直接测试？(y/n)")
        if input().strip().lower() == 'y':
            direct_model_test(query, docs[0].page_content)


if __name__ == "__main__":
    main()