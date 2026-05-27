from fastapi import APIRouter, Depends, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db, UserRbac
from auth_middleware import create_access_token, get_current_user
from config import ROLE_SECRET_RULE
from auth_utils import hash_password, verify_password

router = APIRouter(prefix="/api/user")


class PersonalUpdatePayload(BaseModel):
    user_id: str
    username: str | None = None
    dept_name: str | None = None
    dept_code: str | None = None
    role_level: int | None = None
    status: int | None = None


class PasswordUpdatePayload(BaseModel):
    old_password: str
    new_password: str


@router.post("/login")
def login(
    user_id: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not user:
        return {"code": 400, "msg": "账号不存在"}
    if not verify_password(password, user.password_hash):
        return {"code": 400, "msg": "密码错误"}
    token = create_access_token(user_id)
    return {"code": 200, "token": token, "user_id": user_id, "username": user.username}


@router.get("/info")
def get_user_info(db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    allow_max_secret = ROLE_SECRET_RULE.get(user.role_level, 0)
    return {"user_id": user.user_id, "username": user.username, "dept_name": user.dept_name, "dept_code": user.dept_code, "role_level": user.role_level, "status": user.status, "allow_max_secret": allow_max_secret, "allowed_secret_levels": list(range(allow_max_secret + 1)), "is_admin": int(user.role_level or 0) >= 3 or user.user_id == "admin"}


@router.get("/list")
def list_users(db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    me = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not me or int(me.role_level or 0) < 3 and me.user_id != "admin":
        return {"code": 403, "msg": "无管理员权限"}
    users = db.query(UserRbac).order_by(UserRbac.create_time.desc()).all()
    return {"code": 200, "data": [{"id": u.id, "user_id": u.user_id, "username": u.username, "dept_name": u.dept_name, "dept_code": u.dept_code, "role_level": u.role_level, "status": u.status, "create_time": str(u.create_time)} for u in users]}


@router.post("/update")
def update_user(payload: PersonalUpdatePayload, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    me = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not me or int(me.role_level or 0) < 3 and me.user_id != "admin":
        return {"code": 403, "msg": "无管理员权限"}
    target = db.query(UserRbac).filter(UserRbac.user_id == payload.user_id).first()
    if not target:
        return {"code": 404, "msg": "用户不存在"}
    if payload.username is not None: target.username = payload.username
    if payload.dept_name is not None: target.dept_name = payload.dept_name
    if payload.dept_code is not None: target.dept_code = payload.dept_code
    if payload.role_level is not None: target.role_level = payload.role_level
    if payload.status is not None: target.status = payload.status
    db.commit()
    return {"code": 200, "msg": "用户信息已更新"}


@router.post("/create")
def create_user(payload: PersonalUpdatePayload, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    me = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not me or int(me.role_level or 0) < 3 and me.user_id != "admin":
        return {"code": 403, "msg": "无管理员权限"}
    exists = db.query(UserRbac).filter(UserRbac.user_id == payload.user_id).first()
    if exists:
        return {"code": 400, "msg": "账号已存在"}
    user = UserRbac(user_id=payload.user_id, username=payload.username or payload.user_id, dept_name=payload.dept_name or "", dept_code=payload.dept_code or "", role_level=payload.role_level or 0, password_hash=hash_password("123456"), status=payload.status if payload.status is not None else 1)
    db.add(user)
    db.commit()
    return {"code": 200, "msg": "用户已创建，默认密码为123456"}


@router.delete("/delete/{target_user_id}")
def delete_user(target_user_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    me = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not me or int(me.role_level or 0) < 3 and me.user_id != "admin":
        return {"code": 403, "msg": "无管理员权限"}
    target = db.query(UserRbac).filter(UserRbac.user_id == target_user_id).first()
    if not target:
        return {"code": 404, "msg": "用户不存在"}
    db.delete(target)
    db.commit()
    return {"code": 200, "msg": "用户已删除"}


@router.post("/password")
def change_password(payload: PasswordUpdatePayload, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not verify_password(payload.old_password, user.password_hash):
        return {"code": 400, "msg": "旧密码错误"}
    if len(payload.new_password or "") < 6:
        return {"code": 400, "msg": "新密码长度至少6位"}
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"code": 200, "msg": "密码修改成功"}
