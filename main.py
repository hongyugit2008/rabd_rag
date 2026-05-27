from fastapi import FastAPI, Depends, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel

# 导入原有业务模块
from database import get_db, create_tables, UserRbac, DocPermission, DocAcl
from doc_ingest import ingest_doc_with_rbac
from rag_service import rag_chat

# 导入新增登录鉴权模块
from user_api import router as user_router
from auth_middleware import get_current_user
from config import HOST, PORT, ROLE_SECRET_RULE

import os
import re
import logging
import fix_uuid  # 必须是最第一行

logger = logging.getLogger(__name__)


class AclSavePayload(BaseModel):
    items: list


# 初始化数据库表
create_tables()

app = FastAPI(title="私有化RBAC-RAG智能知识库系统")

# 挂载前端静态页面目录
app.mount("/view", StaticFiles(directory="view"), name="view")

# 注册用户登录相关接口
app.include_router(user_router)

# ============ 前端页面访问路由 ============
@app.get("/")
async def go_login():
    return FileResponse("view/login.html")

@app.get("/chat")
async def go_chat():
    return FileResponse("view/chat.html")

@app.get("/admin")
async def go_admin():
    return FileResponse("view/admin.html")

@app.get("/acl/manage")
async def go_acl_manage():
    return FileResponse("view/acl_manage.html")

@app.get("/acl/logs")
async def go_acl_logs():
    return FileResponse("view/acl_logs.html")

# ============ 文档入库接口（保留不变） ============
@app.get("/api/user/me")
async def get_me(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"code": 404, "msg": "用户不存在"})
    allow_max_secret = ROLE_SECRET_RULE.get(int(user.role_level or 0), 0)
    return JSONResponse(status_code=200, content={
        "code": 200,
        "data": {
            "user_id": user.user_id,
            "username": user.username,
            "dept_name": user.dept_name,
            "role_level": user.role_level,
            "allow_max_secret": allow_max_secret,
        },
    })

@app.get("/api/acl/docs")
async def list_acl_docs(
    keyword: str = "",
    acl_rule: str = "",
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    query = db.query(DocPermission)
    if keyword:
        kw = f"%{keyword.strip()}%"
        query = query.filter(
            (DocPermission.doc_id.like(kw)) |
            (DocPermission.original_filename.like(kw)) |
            (DocPermission.dept_owner.like(kw)) |
            (DocPermission.uploader_id.like(kw))
        )
    docs = query.order_by(DocPermission.create_time.desc()).all()
    results = []
    acl_kw = acl_rule.strip().lower()
    for d in docs:
        acl_items = db.query(DocAcl).filter(DocAcl.doc_permission_id == d.id).all()
        acl_text = " | ".join([f"{a.subject_type}:{a.subject_value}:{a.acl_type}" for a in acl_items])
        if acl_kw and acl_kw not in acl_text.lower():
            continue
        results.append({
            "id": d.id,
            "doc_id": d.doc_id,
            "dept_owner": d.dept_owner,
            "secret_level": d.secret_level,
            "uploader_id": d.uploader_id,
            "original_filename": d.original_filename,
            "acl_summary": acl_text,
        })
    return {"code": 200, "data": results}

@app.get("/api/acl/{doc_permission_id}")
async def get_acl_items(
    doc_permission_id: int,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    items = db.query(DocAcl).filter(DocAcl.doc_permission_id == doc_permission_id).all()
    return {"code": 200, "data": [
        {
            "subject_type": i.subject_type,
            "subject_value": i.subject_value,
            "acl_type": i.acl_type,
        } for i in items
    ]}

@app.post("/api/acl/{doc_permission_id}")
async def save_acl_items(
    doc_permission_id: int,
    payload: AclSavePayload,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    doc = db.query(DocPermission).filter(DocPermission.id == doc_permission_id).first()
    if not doc:
        return JSONResponse(status_code=404, content={"code": 404, "msg": "文档不存在"})

    db.query(DocAcl).filter(DocAcl.doc_permission_id == doc_permission_id).delete()
    rows = []
    for item in payload.items:
        st = (item.get("subject_type") or "").strip()
        sv = (item.get("subject_value") or "").strip()
        at = (item.get("acl_type") or "").strip()
        if not st or not sv or at not in {"allow", "deny"}:
            continue
        rows.append(DocAcl(doc_permission_id=doc_permission_id, subject_type=st, subject_value=sv, acl_type=at))
    if rows:
        db.add_all(rows)
    db.commit()
    return {"code": 200, "msg": "ACL 保存成功", "count": len(rows)}

@app.get("/api/acl/logs")
async def get_acl_logs(
    keyword: str = "",
    user_id: str = Depends(get_current_user)
):
    log_path = os.path.abspath("./acl_audit.log")
    if not os.path.exists(log_path):
        return {"code": 200, "data": []}
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f.readlines()]
    if keyword:
        lines = [line for line in lines if keyword.lower() in line.lower()]
    return {"code": 200, "data": lines[-200:]}

@app.post("/doc/ingest")
async def doc_ingest(
    request: Request,
    file: UploadFile = File(...),
    secret_level: int = Form(1),
    acl_subject_types: str = Form(""),
    acl_subject_values: str = Form(""),
    acl_types: str = Form(""),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    temp_dir = os.path.abspath("./temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)
    logger.info("upload start | user_id=%s | temp_dir=%s | original_filename=%s", user_id, temp_dir, file.filename)
    try:
        user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
        if not user:
            return JSONResponse(status_code=404, content={"code": 404, "msg": "用户不存在"})

        safe_filename = os.path.basename(file.filename or "upload.docx").replace("\\", "_").replace("/", "_")
        file_path = os.path.join(temp_dir, f"{user.user_id}_{safe_filename}")

        allow_max_secret = ROLE_SECRET_RULE.get(int(user.role_level or 0), 0)
        if secret_level > allow_max_secret:
            return JSONResponse(
                status_code=403,
                content={
                    "code": 403,
                    "msg": "无权上传该密级文档",
                    "detail": f"当前最高可上传密级为 {allow_max_secret}",
                },
            )

        file_bytes = await file.read()
        logger.info("upload payload read | user_id=%s | bytes=%s | file_path=%s", user.user_id, len(file_bytes), file_path)
        with open(file_path, "wb") as f:
            written = f.write(file_bytes)
        logger.info("upload file written | user_id=%s | written_bytes=%s | file_exists=%s | file_size=%s", user.user_id, written, os.path.exists(file_path), os.path.getsize(file_path) if os.path.exists(file_path) else -1)

        acl_items = []
        if acl_subject_types and acl_subject_values and acl_types:
            subject_types = [x.strip() for x in acl_subject_types.split(",")]
            subject_values = [x.strip() for x in acl_subject_values.split(",")]
            acl_type_values = [x.strip() for x in acl_types.split(",")]
            for st, sv, at in zip(subject_types, subject_values, acl_type_values):
                acl_items.append({"subject_type": st, "subject_value": sv, "acl_type": at})

        res = ingest_doc_with_rbac(
            db,
            file_path,
            user.user_id,
            user.dept_name,
            secret_level,
            original_filename=safe_filename,
            acl_items=acl_items,
        )
        res["temp_file_path"] = file_path
        return JSONResponse(status_code=200, content=res)
    except ValueError as e:
        logger.exception("upload failed with value error | user_id=%s | file_path=%s", user_id, locals().get("file_path"))
        return JSONResponse(status_code=400, content={"code": 400, "msg": str(e), "error_type": "ValueError"})
    except Exception as e:
        logger.exception("upload failed | user_id=%s | file_path=%s", user_id, locals().get("file_path"))
        return JSONResponse(status_code=500, content={"code": 500, "msg": "文档入库失败", "error_type": type(e).__name__, "detail": str(e)})
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass

# ============ RAG问答接口 增加全局JWT鉴权 ============
@app.post("/rag/chat")
async def chat(
    query: str = Form(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    res = rag_chat(db, user_id, query)
    return res

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
