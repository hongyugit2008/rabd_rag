from sqlalchemy.orm import Session
from database import UserRbac, DocPermission
from config import ROLE_SECRET_RULE

class RBACFilter:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        self.user_info = self._get_user_info()

    # 获取用户身份权限信息
    def _get_user_info(self):
        user = self.db.query(UserRbac).filter(UserRbac.user_id == self.user_id).first()
        if not user:
            return None
        return user

    # 核心：过滤向量切片权限列表
    def filter_vectors(self, doc_id_list: list):
        if not self.user_info:
            return []

        # 用户基础身份
        user_dept = self.user_info.dept_name
        user_role = self.user_info.role_level
        allow_max_secret = ROLE_SECRET_RULE.get(user_role, 0)

        valid_doc_ids = []
        for doc_id in doc_id_list:
            doc = self.db.query(DocPermission).filter(DocPermission.doc_id == doc_id).first()
            if not doc:
                continue

            # 1. 黑名单直接拦截
            if self.user_id in doc.black_list_users.split(","):
                continue

            # 2. 白名单优先兜底
            if doc.white_list_users:
                if self.user_id in doc.white_list_users.split(","):
                    valid_doc_ids.append(doc_id)
                continue

            # 3. 跨部门拦截
            if doc.dept_owner != user_dept and doc.secret_level != 0:
                continue

            # 4. 部门内密级等级拦截
            if doc.secret_level > allow_max_secret:
                continue

            valid_doc_ids.append(doc_id)
        return valid_doc_ids