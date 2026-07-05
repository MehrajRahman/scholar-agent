"""The signed-in user's own data: profile + saved-application pipeline.

Every endpoint is scoped to ``CurrentUser`` and delegates to ``db.repo`` (which
filters by ``user_id``), so a user can only ever see or change their own rows.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from ..auth.deps import CurrentUser
from ..db import APPLICATION_STATUSES, get_session
from ..db import repo

router = APIRouter(prefix="/me", tags=["me"])

Db = Annotated[Session, Depends(get_session)]


# --- Schemas ---------------------------------------------------------------

class ProfileIn(BaseModel):
    full_name: str = ""
    cv_text: str = ""
    data: dict = Field(default_factory=dict)


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    full_name: str
    cv_text: str
    data: dict
    updated_at: object | None = None


class ApplicationCreate(BaseModel):
    title: str = Field(min_length=1)
    opportunity_ref: str | None = None
    institution: str | None = None
    country: str | None = None
    kind: str = "scholarship"
    status: str = "interested"
    deadline: str | None = None
    source_url: str | None = None
    notes: str = ""

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in APPLICATION_STATUSES:
            raise ValueError(f"status must be one of {APPLICATION_STATUSES}")
        return v


class ApplicationUpdate(BaseModel):
    title: str | None = None
    institution: str | None = None
    country: str | None = None
    kind: str | None = None
    status: str | None = None
    deadline: str | None = None
    source_url: str | None = None
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str | None) -> str | None:
        if v is not None and v not in APPLICATION_STATUSES:
            raise ValueError(f"status must be one of {APPLICATION_STATUSES}")
        return v


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    opportunity_ref: str | None
    title: str
    institution: str | None
    country: str | None
    kind: str
    status: str
    deadline: str | None
    source_url: str | None
    notes: str
    created_at: object
    updated_at: object


# --- Profile ---------------------------------------------------------------

@router.get("/profile", response_model=ProfileOut)
def get_profile(user: CurrentUser, session: Db) -> ProfileOut:
    profile = repo.get_profile(session, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no profile yet")
    return ProfileOut.model_validate(profile)


@router.put("/profile", response_model=ProfileOut)
def put_profile(body: ProfileIn, user: CurrentUser, session: Db) -> ProfileOut:
    profile = repo.upsert_profile(
        session, user.id, full_name=body.full_name, cv_text=body.cv_text, data=body.data
    )
    return ProfileOut.model_validate(profile)


# --- Applications (pipeline) -----------------------------------------------

@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(
    user: CurrentUser,
    session: Db,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[ApplicationOut]:
    apps = repo.list_applications(session, user.id, status_filter)
    return [ApplicationOut.model_validate(a) for a in apps]


@router.post("/applications", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(body: ApplicationCreate, user: CurrentUser, session: Db) -> ApplicationOut:
    app = repo.create_application(session, user.id, body.model_dump())
    return ApplicationOut.model_validate(app)


@router.get("/applications/{app_id}", response_model=ApplicationOut)
def get_application(app_id: int, user: CurrentUser, session: Db) -> ApplicationOut:
    app = repo.get_application(session, user.id, app_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")
    return ApplicationOut.model_validate(app)


@router.patch("/applications/{app_id}", response_model=ApplicationOut)
def update_application(
    app_id: int, body: ApplicationUpdate, user: CurrentUser, session: Db
) -> ApplicationOut:
    app = repo.update_application(session, user.id, app_id, body.model_dump(exclude_unset=True))
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")
    return ApplicationOut.model_validate(app)


@router.delete("/applications/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(app_id: int, user: CurrentUser, session: Db) -> None:
    if not repo.delete_application(session, user.id, app_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")
