from sqlalchemy.orm import Session
from database import UserRbac, DocPermission, DocAcl
from config import ROLE_SECRET_RULE
import logging

logger = logging.getLogger(__name__)


class RBACFilter:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        self.user_info = self._get_user_info()

    def _get_user_info(self):
        user = self.db.query(UserRbac).filter(UserRbac.user_id == self.user_id).first()
        if not user:
            return None
        return user

    def _doc_acl_items(self, doc_id: str):
        doc_perm = self.db.query(DocPermission).filter(DocPermission.doc_id == doc_id).first()
        if not doc_perm:
            return []
        return doc_perm, self.db.query(DocAcl).filter(DocAcl.doc_permission_id == doc_perm.id).all()

    def _match_acl_subject(self, item: DocAcl) -> bool:
        user_id = self.user_id
        dept_name = self.user_info.dept_name if self.user_info else ""
        role_level = str(self.user_info.role_level if self.user_info else 0)

        if item.subject_type == "user":
            return item.subject_value == user_id
        if item.subject_type == "dept":
            return item.subject_value == dept_name
        if item.subject_type == "role":
            return item.subject_value == role_level
        return False

    def _is_allowed_by_acl(self, doc_id: str):
        result = self._doc_acl_items(doc_id)
        if not result:
            return True, "no_acl"
        doc_perm, acl_items = result
        if not acl_items:
            return True, "no_acl"

        deny_hit = [item for item in acl_items if item.acl_type == "deny" and self._match_acl_subject(item)]
        if deny_hit:
            logger.info(
                "acl deny hit | user_id=%s | doc_id=%s | doc_permission_id=%s | subject=%s:%s",
                self.user_id,
                doc_id,
                doc_perm.id,
                deny_hit[0].subject_type,
                deny_hit[0].subject_value,
            )
            return False, "deny"

        allow_items = [item for item in acl_items if item.acl_type == "allow"]
        if allow_items:
            matched = [item for item in allow_items if self._match_acl_subject(item)]
            if matched:
                logger.info(
                    "acl allow hit | user_id=%s | doc_id=%s | doc_permission_id=%s | subject=%s:%s",
                    self.user_id,
                    doc_id,
                    doc_perm.id,
                    matched[0].subject_type,
                    matched[0].subject_value,
                )
                return True, "allow"
            logger.info(
                "acl allow miss | user_id=%s | doc_id=%s | doc_permission_id=%s",
                self.user_id,
                doc_id,
                doc_perm.id,
            )
            return False, "allow_miss"

        return True, "no_acl"

    # 核心：过滤向量切片权限列表
    def filter_vectors(self, doc_id_list: list):
        if not self.user_info:
            return []

        user_dept = self.user_info.dept_name
        user_role = self.user_info.role_level
        allow_max_secret = ROLE_SECRET_RULE.get(user_role, 0)

        valid_doc_ids = []
        for doc_id in doc_id_list:
            doc = self.db.query(DocPermission).filter(DocPermission.doc_id == doc_id).first()
            if not doc:
                continue

            acl_allowed, acl_reason = self._is_allowed_by_acl(doc_id)
            if not acl_allowed:
                logger.info(
                    "doc filtered by acl | user_id=%s | doc_id=%s | reason=%s",
                    self.user_id,
                    doc_id,
                    acl_reason,
                )
                continue

            if doc.dept_owner != user_dept and doc.secret_level != 0:
                logger.info(
                    "doc filtered by dept | user_id=%s | doc_id=%s | user_dept=%s | doc_dept=%s | secret_level=%s",
                    self.user_id,
                    doc_id,
                    user_dept,
                    doc.dept_owner,
                    doc.secret_level,
                )
                continue
            if doc.secret_level > allow_max_secret:
                logger.info(
                    "doc filtered by secret | user_id=%s | doc_id=%s | secret_level=%s | allow_max_secret=%s",
                    self.user_id,
                    doc_id,
                    doc.secret_level,
                    allow_max_secret,
                )
                continue

            valid_doc_ids.append(doc_id)
            logger.info(
                "doc allowed | user_id=%s | doc_id=%s | dept=%s | secret_level=%s",
                self.user_id,
                doc_id,
                doc.dept_owner,
                doc.secret_level,
            )
        return valid_doc_ids
