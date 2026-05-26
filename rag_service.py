import logging
from sqlalchemy.orm import Session
from openai import OpenAI
from rbac_middleware import RBACFilter
from database import DocPermission, DocAcl
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


def _acl_match_subject(item: DocAcl, user_id: str, dept_name: str, role_level: int) -> bool:
    role_level_str = str(role_level)
    if item.subject_type == "user":
        return item.subject_value == user_id
    if item.subject_type == "dept":
        return item.subject_value == dept_name
    if item.subject_type == "role":
        return item.subject_value == role_level_str
    return False


def _get_acl_candidate_doc_ids(db: Session, user_id: str, dept_name: str, role_level: int):
    """先在数据库里筛出当前用户可访问的 doc_id，再去 Chroma 召回。"""
    docs = db.query(DocPermission).all()
    allowed_doc_ids = []
    for doc in docs:
        acl_items = db.query(DocAcl).filter(DocAcl.doc_permission_id == doc.id).all()
        if not acl_items:
            allowed_doc_ids.append(doc.doc_id)
            logger.info("acl prefilter allow by default | doc_id=%s | reason=no_acl", doc.doc_id)
            continue

        deny_hit = next((item for item in acl_items if item.acl_type == "deny" and _acl_match_subject(item, user_id, dept_name, role_level)), None)
        if deny_hit:
            logger.info(
                "acl prefilter deny | user_id=%s | doc_id=%s | doc_permission_id=%s | subject=%s:%s",
                user_id,
                doc.doc_id,
                doc.id,
                deny_hit.subject_type,
                deny_hit.subject_value,
            )
            continue

        allow_items = [item for item in acl_items if item.acl_type == "allow"]
        if allow_items:
            matched = next((item for item in allow_items if _acl_match_subject(item, user_id, dept_name, role_level)), None)
            if matched:
                allowed_doc_ids.append(doc.doc_id)
                logger.info(
                    "acl prefilter allow | user_id=%s | doc_id=%s | doc_permission_id=%s | subject=%s:%s",
                    user_id,
                    doc.doc_id,
                    doc.id,
                    matched.subject_type,
                    matched.subject_value,
                )
            else:
                logger.info(
                    "acl prefilter allow-miss | user_id=%s | doc_id=%s | doc_permission_id=%s",
                    user_id,
                    doc.doc_id,
                    doc.id,
                )
            continue

        allowed_doc_ids.append(doc.doc_id)
        logger.info("acl prefilter allow by default | doc_id=%s | reason=no_allow_rules", doc.doc_id)

    return allowed_doc_ids


def _retrieve_chunks(query: str, dept_name: str, role_level: int, db: Session, user_id: str):
    """先按 ACL 过滤可访问文档，再检索 Chroma，并做密级/部门兜底。"""
    allow_max_secret = ROLE_SECRET_RULE.get(role_level, 0)
    rbac = RBACFilter(db, user_id)
    allowed_doc_ids = _get_acl_candidate_doc_ids(db, user_id, dept_name, role_level)

    if not allowed_doc_ids:
        logger.warning("acl prefilter returned no doc ids | user_id=%s", user_id)
        return []

    candidates = []
    try:
        # Chroma 的 metadata filter 对大集合不友好，这里只做部门过滤，ACL 已前置到数据库层
        candidates = vector_db.similarity_search(query, k=20, filter={"dept_owner": dept_name})
        logger.info("dept filtered search hits=%s | dept=%s", len(candidates), dept_name)
    except Exception:
        logger.exception("dept filtered search failed | dept=%s", dept_name)

    if not candidates:
        try:
            candidates = vector_db.similarity_search(query, k=20)
            logger.info("fallback global search hits=%s", len(candidates))
        except Exception:
            logger.exception("global search failed | user_id=%s", user_id)
            return []

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

        if not doc_id or doc_id not in allowed_doc_ids:
            continue
        if doc_dept != dept_name and secret_level != 0:
            logger.info(
                "chunk filtered by dept | user_id=%s | doc_id=%s | user_dept=%s | doc_dept=%s | secret_level=%s",
                user_id,
                doc_id,
                dept_name,
                doc_dept,
                secret_level,
            )
            continue
        if secret_level > allow_max_secret:
            logger.info(
                "chunk filtered by secret | user_id=%s | doc_id=%s | secret_level=%s | allow_max_secret=%s",
                user_id,
                doc_id,
                secret_level,
                allow_max_secret,
            )
            continue
        logger.info(
            "chunk allowed | user_id=%s | doc_id=%s | dept=%s | secret_level=%s",
            user_id,
            doc_id,
            doc_dept,
            secret_level,
        )
        valid_chunks.append(item)

    logger.info("acl prefiltered doc_ids=%s | valid_chunks=%s", len(allowed_doc_ids), len(valid_chunks))
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

        valid_chunks = _retrieve_chunks(query, rbac.user_info.dept_name, rbac.user_info.role_level, db, user_id)
        logger.info("valid_chunks=%s", len(valid_chunks))

        if not valid_chunks:
            logger.warning(
                "no valid chunks for user_id=%s | dept=%s | role_level=%s",
                user_id,
                rbac.user_info.dept_name,
                rbac.user_info.role_level,
            )
            return {"code": 200, "data": "暂无相关资料"}

        context = "\n".join([page.page_content for page in valid_chunks])
        logger.info("context_len=%s", len(context))

        prompt = f"""
你是企业内部智能办公助手，严格遵守数据权限规则：
1. 仅基于给定上下文回答，禁止编造、推演、猜测涉密数据
2. 禁止输出跨部门涉密信息、底价、成本、薪资等敏感内容
3. 无明确信息时直接回复「暂无相关资料」

上下文：{context}
用户问题：{query}
"""
        logger.info("prompt_len=%s", len(prompt))

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
