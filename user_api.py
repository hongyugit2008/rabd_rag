from fastapi import APIRouter, Depends, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import get_db, UserRbac, UserDeptRelation
from auth_middleware import create_access_token, get_current_user
from config import ROLE_SECRET_RULE, SUPER_ADMIN_ROLE_LEVEL
from auth_utils import hash_password, verify_password

router = APIRouter(prefix="/api/user")


class PasswordUpdatePayload(BaseModel):
    old_password: str
    new_password: str


class AdminCreatePayload(BaseModel):
    user_id: str
    username: str | None = None
    dept_names: list[str] = Field(default_factory=list)
    dept_code: str | None = None
    role_level: int
    password: str | None = None
    status: int | None = 1


class UserUpdatePayload(BaseModel):
    user_id: str
    username: str | None = None
    dept_name: str | None = None
    dept_code: str | None = None
    role_level: int | None = None
    status: int | None = None
    dept_names: list[str] | None = None


def _is_super_admin(user: UserRbac | None) -> bool:
    return bool(user) and (user.user_id == "admin" or int(user.role_level or 0) >= SUPER_ADMIN_ROLE_LEVEL)


def _max_creatable_role(me: UserRbac) -> int:
    return SUPER_ADMIN_ROLE_LEVEL if _is_super_admin(me) else int(me.role_level or 0)


def _get_user_depts(db: Session, user: UserRbac) -> list[UserDeptRelation]:
    rows = db.query(UserDeptRelation).filter(UserDeptRelation.user_id == user.user_id).all()
    if rows:
        return rows
    if user.dept_name:
        fallback = UserDeptRelation(user_id=user.user_id, dept_name=user.dept_name, dept_code=user.dept_code or "", is_primary=1)
        return [fallback]
    return []


def _allowed_depts_for_creator(db: Session, me: UserRbac) -> set[str]:
    if _is_super_admin(me):
        return set()
    return {row.dept_name for row in _get_user_depts(db, me)}


@router.post("/login")
def login(user_id: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not user:
        return {"code": 400, "msg": "账号不存在"}
    if user.status != 1:
        return {"code": 403, "msg": "账号已禁用"}
    if not verify_password(password, user.password_hash):
        return {"code": 400, "msg": "密码错误"}
    token = create_access_token(user_id)
    return {"code": 200, "token": token, "user_id": user_id, "username": user.username}


@router.get("/info")
def get_user_info(db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    allow_max_secret = ROLE_SECRET_RULE.get(int(user.role_level or 0), 0)
    depts = _get_user_depts(db, user)
    dept_names = [r.dept_name for r in depts]
    dept_codes = [r.dept_code for r in depts]
    return {"user_id": user.user_id, "username": user.username, "dept_name": user.dept_name, "dept_code": user.dept_code, "dept_names": dept_names, "dept_codes": dept_codes, "role_level": user.role_level, "status": user.status, "allow_max_secret": allow_max_secret, "allowed_secret_levels": list(range(allow_max_secret + 1)), "is_admin": _is_super_admin(user) or int(user.role_level or 0) >= 2}


@router.get("/list")
def list_users(db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    me = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not _is_super_admin(me) and int(me.role_level or 0) < 2:
        return {"code": 403, "msg": "无管理员权限"}
    query = db.query(UserRbac)
    if not _is_super_admin(me):
        allowed = _allowed_depts_for_creator(db, me)
        if allowed:
            dept_users = db.query(UserDeptRelation.user_id).filter(UserDeptRelation.dept_name.in_(list(allowed))).distinct().subquery()
            query = query.filter(UserRbac.user_id.in_(db.query(dept_users.c.user_id)))
        else:
            query = query.filter(UserRbac.dept_name == (me.dept_name or ""))
    users = query.order_by(UserRbac.create_time.desc()).all()
    data = []
    for u in users:
        depts = _get_user_depts(db, u)
        data.append({
            "id": u.id,
            "user_id": u.user_id,
            "username": u.username,
            "dept_name": u.dept_name,
            "dept_code": u.dept_code,
            "dept_names": [r.dept_name for r in depts],
            "dept_codes": [r.dept_code for r in depts],
            "role_level": u.role_level,
            "status": u.status,
            "create_time": str(u.create_time),
        })
    return {"code": 200, "data": data}


@router.post("/create-admin")
def create_admin(payload: AdminCreatePayload, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    me = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not me:
        return {"code": 401, "msg": "未登录"}
    if payload.role_level >= _max_creatable_role(me):
        return {"code": 403, "msg": "新增管理员权限不能高于你的权限"}
    if payload.role_level < 2:
        return {"code": 400, "msg": "仅允许创建部门管理员及以上等级"}

    dept_names = [d.strip() for d in (payload.dept_names or []) if d and d.strip()]
    if _is_super_admin(me):
        if not dept_names:
            return {"code": 400, "msg": "超级管理员创建时需要指定至少一个部门"}
    else:
        allowed = _allowed_depts_for_creator(db, me)
        if dept_names:
            if any(d not in allowed for d in dept_names):
                return {"code": 403, "msg": "只能创建本部门管理员"}
        else:
            dept_names = list(allowed)[:1]
        if not dept_names:
            return {"code": 400, "msg": "当前账号未绑定可管理部门"}

    exists = db.query(UserRbac).filter(UserRbac.user_id == payload.user_id).first()
    if exists:
        return {"code": 400, "msg": "账号已存在"}

    password = payload.password or "1234567"
    primary_dept = dept_names[0]
    user = UserRbac(
        user_id=payload.user_id,
        username=payload.username or payload.user_id,
        dept_name=primary_dept,
        dept_code=payload.dept_code or primary_dept,
        role_level=payload.role_level,
        password_hash=hash_password(password),
        status=payload.status if payload.status is not None else 1,
    )
    db.add(user)
    db.flush()
    db.query(UserDeptRelation).filter(UserDeptRelation.user_id == payload.user_id).delete()
    for idx, dept_name in enumerate(dept_names):
        db.add(UserDeptRelation(
            user_id=payload.user_id,
            dept_name=dept_name,
            dept_code=payload.dept_code or dept_name,
            is_primary=1 if idx == 0 else 0,
        ))
    db.commit()
    return {"code": 200, "msg": "管理员创建成功", "default_password": password, "scope_depts": dept_names}


@router.post("/update")
def update_user(payload: UserUpdatePayload, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    me = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not _is_super_admin(me) and int(me.role_level or 0) < 2:
        return {"code": 403, "msg": "无管理员权限"}
    target = db.query(UserRbac).filter(UserRbac.user_id == payload.user_id).first()
    if not target:
        return {"code": 404, "msg": "用户不存在"}
    if not _is_super_admin(me):
        allowed = _allowed_depts_for_creator(db, me)
        target_depts = {r.dept_name for r in _get_user_depts(db, target)}
        if target_depts and not target_depts.issubset(allowed):
            return {"code": 403, "msg": "只能管理本部门用户"}
    if payload.username is not None:
        target.username = payload.username
    if payload.dept_name is not None:
        target.dept_name = payload.dept_name
    if payload.dept_code is not None:
        target.dept_code = payload.dept_code
    if payload.role_level is not None:
        if payload.role_level >= _max_creatable_role(me):
            return {"code": 403, "msg": "不能设置高于自己的权限"}
        target.role_level = payload.role_level
    if payload.status is not None:
        target.status = payload.status
    if payload.dept_names is not None:
        dept_names = [d.strip() for d in payload.dept_names if d and d.strip()]
        if not _is_super_admin(me):
            allowed = _allowed_depts_for_creator(db, me)
            if any(d not in allowed for d in dept_names):
                return {"code": 403, "msg": "只能管理本部门用户"}
        db.query(UserDeptRelation).filter(UserDeptRelation.user_id == target.user_id).delete()
        for idx, dept_name in enumerate(dept_names):
            db.add(UserDeptRelation(user_id=target.user_id, dept_name=dept_name, dept_code=payload.dept_code or dept_name, is_primary=1 if idx == 0 else 0))
        if dept_names:
            target.dept_name = dept_names[0]
    db.commit()
    return {"code": 200, "msg": "用户信息已更新"}


@router.delete("/delete/{target_user_id}")
def delete_user(target_user_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    me = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not _is_super_admin(me) and int(me.role_level or 0) < 2:
        return {"code": 403, "msg": "无管理员权限"}
    target = db.query(UserRbac).filter(UserRbac.user_id == target_user_id).first()
    if not target:
        return {"code": 404, "msg": "用户不存在"}
    if target.user_id == "admin":
        return {"code": 403, "msg": "不能删除超级管理员"}
    if not _is_super_admin(me):
        allowed = _allowed_depts_for_creator(db, me)
        target_depts = {r.dept_name for r in _get_user_depts(db, target)}
        if target_depts and not target_depts.issubset(allowed):
            return {"code": 403, "msg": "只能管理本部门用户"}
    db.query(UserDeptRelation).filter(UserDeptRelation.user_id == target_user_id).delete()
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
