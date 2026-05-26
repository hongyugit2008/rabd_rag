from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import *
import datetime

# 数据库连接初始化
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 1. 用户权限表 user_rbac
class UserRbac(Base):
    __tablename__ = "user_rbac"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), unique=True, nullable=False)
    username = Column(String(50))
    dept_name = Column(String(50))
    dept_code = Column(String(50))
    role_level = Column(Integer, default=0)
    privilege_tag = Column(String(200), default="")
    status = Column(Integer, default=1)
    create_time = Column(DateTime, default=datetime.datetime.now)

# 2. 文档权限表 doc_permission
class DocPermission(Base):
    __tablename__ = "doc_permission"
    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(String(50), unique=True, nullable=False)
    vec_group_id = Column(String(50))
    dept_owner = Column(String(50))
    secret_level = Column(Integer, default=1)
    white_list_users = Column(String(1000), default="")
    black_list_users = Column(String(1000), default="")
    is_allow_summary = Column(Integer, default=1)
    is_allow_export = Column(Integer, default=1)
    uploader_id = Column(String(50))
    create_time = Column(DateTime, default=datetime.datetime.now)

# 3. 权限映射规则表 rbac_rule
class RbacRule(Base):
    __tablename__ = "rbac_rule"
    id = Column(Integer, primary_key=True, index=True)
    role_level = Column(Integer)
    allow_secret_level = Column(Integer)
    allow_dept_list = Column(String(200), default="")
    is_cross_dept_query = Column(Integer, default=0)

# 创建所有数据表
def create_tables():
    Base.metadata.create_all(bind=engine)

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()