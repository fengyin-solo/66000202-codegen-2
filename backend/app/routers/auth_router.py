from fastapi import APIRouter, Header, HTTPException
from app.models.schemas import LoginRequest
from app.services import auth_service

router = APIRouter()


@router.post("/auth/login")
def login(req: LoginRequest):
    result = auth_service.login(req.username, req.password)
    if not result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return result


@router.get("/auth/me")
def me(authorization: str = Header(None)):
    user = auth_service.user_from_authorization(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user
