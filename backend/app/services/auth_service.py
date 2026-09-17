"""操作者身份与角色管理（演示用内存实现，生产环境应替换为真实认证体系）。

角色：
- operator: 具备写入归属的操作者，可提交点位下发并回看下发记录
- viewer:   只读查看者，仅可查看实时读数，不能改动任何点位
"""
import uuid
from typing import Any, Dict, Optional

USERS: Dict[str, Dict[str, Any]] = {
    "operator1": {"password": "operator123", "role": "operator", "display_name": "张工"},
    "operator2": {"password": "operator123", "role": "operator", "display_name": "李工"},
    "viewer1": {"password": "viewer123", "role": "viewer", "display_name": "王工"},
}

_TOKENS: Dict[str, str] = {}  # token -> username


def login(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = USERS.get(username)
    if not user or user["password"] != password:
        return None
    token = uuid.uuid4().hex
    _TOKENS[token] = username
    return {
        "token": token,
        "user": {"username": username, "role": user["role"], "display_name": user["display_name"]},
    }


def get_user(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    username = _TOKENS.get(token)
    if not username:
        return None
    user = USERS[username]
    return {"username": username, "role": user["role"], "display_name": user["display_name"]}


def user_from_authorization(authorization: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse 'Authorization: Bearer <token>' header into a user dict."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return get_user(parts[1].strip())


def logout(token: str) -> None:
    _TOKENS.pop(token, None)
