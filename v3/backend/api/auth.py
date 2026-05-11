import hashlib, uuid, time
from fastapi import APIRouter, HTTPException, Header
from database import get_db
from config import SECRET_KEY

router = APIRouter(prefix="/api/auth", tags=["auth"])

_sessions = {}

def hash_password(pw):
    return hashlib.sha256(f"{pw}{SECRET_KEY}".encode()).hexdigest()

def create_session(username, role="user"):
    token = str(uuid.uuid4())
    _sessions[token] = {"username": username, "role": role, "created": time.time()}
    return token

def get_user(authorization: str = Header(None)):
    """Returns username string (for backward compat)"""
    s = _get_session(authorization)
    return s["username"]

def _get_session(authorization: str = Header(None)):
    """Returns full session dict with username and role"""
    if not authorization: raise HTTPException(401, "未登录")
    token = authorization.replace("Bearer ", "")
    s = _sessions.get(token)
    if not s or time.time() - s["created"] > 86400:
        raise HTTPException(401, "登录已过期")
    return s

@router.post("/login")
def login(data: dict):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE username=?", (data["username"],)).fetchone()
    conn.close()
    if u and u["password_hash"] == hash_password(data["password"]):
        token = create_session(data["username"], u["role"])
        return {"token": token, "username": data["username"], "role": u["role"]}
    raise HTTPException(401, "用户名或密码错误")

@router.post("/register")
def register(data: dict):
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?,?)",
                     (data["username"], hash_password(data["password"])))
        conn.commit()
        return {"token": create_session(data["username"], "user"), "username": data["username"], "role": "user"}
    except:
        raise HTTPException(400, "用户名已存在")
    finally:
        conn.close()

@router.get("/me")
def me(authorization: str = Header(None)):
    s = _get_session(authorization)
    return {"username": s["username"], "role": s["role"]}
