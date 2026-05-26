import logging
from sqlalchemy.orm import Session
from openai import OpenAI
from rbac_middleware import RBACFilter
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODE, ROLE_SECRET_RULE
from doc_ingest import vector_db


logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


client = OpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL.rstrip("/"),
)


def _retrieve_chunks(query: str, dept_name: str, role_level: int):
    """优先在用户部门内检索，再回退到全局检索。"""
    allow_max_secret = ROLE_SECRET_RULE.get(role_level, 0)

    candidates = []
    try:
        candidates = vector_db.similarity_search(query, k=20, filter={"dept_owner": dept_name})
        logger.info("dept filtered search hits=%s | dept=%s", len(candidates), dept_name)
    except Exception:
        logger.exception("dept filtered search failed | dept=%s", dept_name)

    if not candidates:
        candidates = vector_db.similarity_search(query, k=20)
        logger.info("fallback global search hits=%s", len(candidates))

    valid_chunks = []
    for idx, item in enumerate(candidates):
        doc_id = item.metadata.get("doc_id")
        doc_dept = item.metadata.get("dept_owner")
        secret_level = int(item.metadata.get("secret_level", 0) or 0)
        logger.info(
            "retrieved hit[%s] | doc_id=%s | dept_owner=%s | secret_level=%s | preview=%s",
            idx,
            doc_id,
            doc_dept,
            secret_level,
            (item.page_content or "")[:80].replace("\n", " "),
        )

        # 部门内优先；如果回退到了全局检索，也仍按权限规则过滤
        if doc_dept != dept_name and secret_level != 0:
            continue
        if secret_level > allow_max_secret:
            continue
        valid_chunks.append(item)

    return valid_chunks


# RAG问答核心逻辑
def rag_chat(db: Session, user_id: str, query: str):
    logger.info(
        "rag_chat start | user_id=%s | query_len=%s | model=%s | base_url=%s",
        user_id,
        len(query or ""),
        LLM_MODE,
        LLM_BASE_URL,
    )
    try:
        # 1. 初始化权限过滤器
        rbac = RBACFilter(db, user_id)
        if rbac.user_info:
            logger.info(
                "rbac user_info | user_id=%s | dept=%s | role_level=%s | status=%s",
                rbac.user_info.user_id,
                rbac.user_info.dept_name,
                rbac.user_info.role_level,
                rbac.user_info.status,
            )
        else:
            logger.warning("user has no permission | user_id=%s", user_id)
            return {"code": 403, "msg": "用户无权限"}

        # 2. 权限感知检索：先按部门召回，再按密级过滤
        valid_chunks = _retrieve_chunks(query, rbac.user_info.dept_name, rbac.user_info.role_level)
        logger.info("valid_chunks=%s", len(valid_chunks))

        if not valid_chunks:
            logger.warning(
                "no valid chunks for user_id=%s | dept=%s | role_level=%s",
                user_id,
                rbac.user_info.dept_name,
                rbac.user_info.role_level,
            )
            return {"code": 200, "data": "暂无相关资料"}

        # 3. 拼接上下文
        context = "\n".join([page.page_content for page in valid_chunks])
        logger.info("context_len=%s", len(context))

        # 4. LLM权限约束Prompt
        prompt = f"""
你是企业内部智能办公助手，严格遵守数据权限规则：
1. 仅基于给定上下文回答，禁止编造、推演、猜测涉密数据
2. 禁止输出跨部门涉密信息、底价、成本、薪资等敏感内容
3. 无明确信息时直接回复「暂无相关资料」

上下文：{context}
用户问题：{query}
"""
        logger.info("prompt_len=%s", len(prompt))

        # 5. 生成答案（与 llm_smoke_test.py 保持完全一致的调用方式）
        response = client.chat.completions.create(
            model=LLM_MODE,
            messages=[
                {"role": "system", "content": "你是一个用于企业知识库问答的助手。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        answer = response.choices[0].message.content or "暂无相关资料"
        logger.info("llm success | answer_len=%s", len(answer))
        return {"code": 200, "data": answer}
    except Exception as e:
        logger.exception("rag_chat failed | user_id=%s | query=%s", user_id, query)
        return {"code": 500, "msg": f"问答服务异常：{e}"}
