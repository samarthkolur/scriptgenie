"""The signed-in user's own profile.

The smallest authenticated route in the service, and the one the web app calls
first: it is how the browser confirms that the session cookie it holds actually
produces a verified caller on this side, rather than assuming so because a
cookie exists.

It reads the profile through the caller's own token, so the row it returns is
the row row level security allows — which for this table is exactly one.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import Db
from app.core.errors import NotFoundError
from app.core.security import CurrentUser

router = APIRouter(tags=["account"])


class Profile(BaseModel):
    """The account as the product knows it.

    The access token is not here and never will be. It reaches this service in
    a header and is used to call the database; putting it in a response body
    would put it in browser caches, logs and screenshots.
    """

    id: str
    email: str
    display_name: str | None
    avatar_url: str | None
    created_at: datetime


@router.get("/me", response_model=Profile, summary="The signed-in user's profile")
async def read_me(user: CurrentUser, db: Db) -> Profile:
    row = await db.select_one("profiles", user=user, params={"id": f"eq.{user.id}"})
    if row is None:
        # The profile is created by a database trigger on signup, so its
        # absence means the trigger did not run — a deployment that applied
        # some migrations and not others. Saying so beats a bare 404 that
        # invites the caller to retry.
        raise NotFoundError(
            "no profile exists for this account; the signup trigger has not run "
            "against this database"
        )
    return Profile(
        id=str(row["id"]),
        email=str(row["email"]),
        display_name=row.get("display_name"),
        avatar_url=row.get("avatar_url"),
        created_at=row["created_at"],
    )
