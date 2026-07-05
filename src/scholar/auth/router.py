"""Auth endpoints: signup, login, and 'who am I'."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_session
from . import service
from .deps import CurrentUser
from .security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8, description="at least 8 characters")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str


class MeResponse(BaseModel):
    user_id: int
    email: str


@router.post("/signup", response_model=TokenResponse)
def signup(body: Credentials, session: Annotated[Session, Depends(get_session)]) -> TokenResponse:
    try:
        user = service.create_user(session, body.email, body.password)
    except service.AuthError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return TokenResponse(access_token=create_access_token(user.id), user_id=user.id, email=user.email)


@router.post("/login", response_model=TokenResponse)
def login(body: Credentials, session: Annotated[Session, Depends(get_session)]) -> TokenResponse:
    user = service.authenticate(session, body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id), user_id=user.id, email=user.email)


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> MeResponse:
    return MeResponse(user_id=user.id, email=user.email)
