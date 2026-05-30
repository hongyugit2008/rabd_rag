from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from config import ROLE_SECRET_RULE
from database import DocAcl, DocPermission, UserRbac


@dataclass
class AccessScope:
    ok: bool
    msg: str = ''
    is_admin: bool = False
    user_id: str = ''
    dept_name: str = ''
    role_level: int = 0
    allow_max_secret: int = 0


def get_access_scope(db: Session, user_id: str) -> dict[str, Any]:
    user = db.query(UserRbac).filter(UserRbac.user_id == user_id).first()
    if not user:
        return {'ok': False, 'msg': '用户不存在'}
    role_level = int(user.role_level or 0)
    allow_max_secret = ROLE_SECRET_RULE.get(role_level, 0)
    is_admin = role_level >= 3 or user.user_id == 'admin'
    return {
        'ok': True,
        'is_admin': is_admin,
        'user_id': user.user_id,
        'dept_name': user.dept_name or '',
        'role_level': role_level,
        'allow_max_secret': allow_max_secret,
    }


def _match_acl_subject(item: DocAcl, user_id: str, dept_name: str, role_level: int) -> bool:
    if item.subject_type == 'user':
        return item.subject_value == user_id
    if item.subject_type == 'dept':
        return item.subject_value == dept_name
    if item.subject_type == 'role':
        return item.subject_value == str(role_level)
    return False


def can_view_doc(db: Session, user_id: str, doc: DocPermission) -> tuple[bool, str]:
    scope = get_access_scope(db, user_id)
    if not scope['ok']:
        return False, scope['msg']

    if int(doc.is_deleted or 0) == 1:
        return False, 'deleted'

    if scope['is_admin']:
        return True, 'admin'

    dept_name = scope['dept_name']
    role_level = scope['role_level']
    allow_max_secret = scope['allow_max_secret']

    acl_items = db.query(DocAcl).filter(DocAcl.doc_permission_id == doc.id).all()
    if acl_items:
        deny_hit = next((item for item in acl_items if item.acl_type == 'deny' and _match_acl_subject(item, user_id, dept_name, role_level)), None)
        if deny_hit:
            return False, 'deny'
        allow_items = [item for item in acl_items if item.acl_type == 'allow']
        if allow_items:
            matched = next((item for item in allow_items if _match_acl_subject(item, user_id, dept_name, role_level)), None)
            if not matched:
                return False, 'allow_miss'

    if doc.dept_owner != dept_name and doc.secret_level != 0:
        return False, 'dept'
    if int(doc.secret_level or 0) > allow_max_secret:
        return False, 'secret'
    return True, 'ok'


def list_visible_doc_ids(db: Session, user_id: str) -> list[str]:
    scope = get_access_scope(db, user_id)
    if not scope['ok']:
        return []
    docs = db.query(DocPermission).filter(DocPermission.is_deleted == 0).all()
    if scope['is_admin']:
        return [doc.doc_id for doc in docs]
    visible = []
    for doc in docs:
        ok, _ = can_view_doc(db, user_id, doc)
        if ok:
            visible.append(doc.doc_id)
    return visible
