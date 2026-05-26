from fastapi import Request, HTTPException
import jwt
from datetime import datetime, timedelta
from config import *

# JWT配置
SECRET_KEY = "rag-rbac-secret-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

def create_access_token(user_id: str):
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token

async def get_current_user(request: Request) -> str:
    """从请求头Token解析user_id，替代IM身份"""
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="身份无效")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="非法令牌")