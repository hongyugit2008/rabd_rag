from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session
from database import get_db, UserRbac
from auth_middleware import create_access_token, get_current_user
from config import ROLE_SECRET_RULE

router = APIRouter(prefix="/api/user")


# 账号密码登录
@router.post("/login")
def login(
    user_id: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not user:
        return {"code": 400, "msg": "账号不存在"}
    # 简易密码校验：实际项目可加密存储
    if password != "123456":
        return {"code": 400, "msg": "密码错误"}
    token = create_access_token(user_id)
    return {"code": 200, "token": token, "user_id": user_id, "username": user.username}


# 获取当前用户信息
@router.get("/info")
def get_user_info(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    allow_max_secret = ROLE_SECRET_RULE.get(user.role_level, 0)
    return {
        "user_id": user.user_id,
        "username": user.username,
        "dept_name": user.dept_name,
        "role_level": user.role_level,
        "allow_max_secret": allow_max_secret,
        "allowed_secret_levels": list(range(allow_max_secret + 1)),
    }
