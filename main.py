from fastapi import FastAPI, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

# 导入原有业务模块
from database import get_db, create_tables
from doc_ingest import ingest_doc_with_rbac
from rag_service import rag_chat

# 导入新增登录鉴权模块
from user_api import router as user_router
from auth_middleware import get_current_user
from config import HOST, PORT

import os
import fix_uuid  # 必须是最第一行


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

# ============ 文档入库接口（保留不变） ============
@app.post("/doc/ingest")
async def doc_ingest(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    dept_owner: str = Form(...),
    secret_level: int = Form(1),
    db: Session = Depends(get_db)
):
    temp_dir = "./temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, file.filename)

    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())

        res = ingest_doc_with_rbac(db, file_path, user_id, dept_owner, secret_level)
        return JSONResponse(status_code=200, content=res)
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "msg": str(e), "error_type": "ValueError"},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "msg": "文档入库失败",
                "error_type": type(e).__name__,
                "detail": str(e),
            },
        )
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