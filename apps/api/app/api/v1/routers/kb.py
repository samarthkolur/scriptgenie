"""The knowledge base as the constraint wizard needs it.

One endpoint, one request, everything the wizard renders. These options are
always needed together — a wizard whose budget step arrives after its genre
step is a wizard that flickers — and every one of them is derived from the same
loaded knowledge base, so splitting them would multiply requests without
splitting any work.

Read-only and pure: no database, no model, no writes. It projects the loaded
knowledge base into wire shapes and stops. What it deliberately does *not*
expose is the rule set: conflict rules are evaluated server-side and their
verdicts are returned as conflicts, because a client that had the rules could
render its own verdict and disagree with the endpoint that enforces it.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import Kb
from app.api.v1 import schemas
from app.core.security import REQUIRE_USER
from app.kb.loader import KnowledgeBase

router = APIRouter(prefix="/kb", tags=["knowledge base"], dependencies=[REQUIRE_USER])

#: The knowledge base ships with the repository and changes only when a
#: deployment does, so a client may hold it for a while. Kept modest rather
#: than long: a stale wizard offering a genre the server has dropped is a
#: confusing failure, and an hour bounds that to the length of one session.
CACHE_CONTROL = "private, max-age=3600"


@router.get(
    "/options",
    response_model=schemas.KbOptions,
    summary="Genres, ratings, budget tiers, territories and archetypes",
)
def read_options(kb: Kb, response: Response) -> schemas.KbOptions:
    response.headers["Cache-Control"] = CACHE_CONTROL
    # The version is part of the cache key from the client's point of view: a
    # deployment that changes the knowledge base changes this string, and a
    # client comparing it knows its cached copy is stale.
    response.headers["ETag"] = f'W/"kb-{kb.version}"'
    return _options(kb)


def _options(kb: KnowledgeBase) -> schemas.KbOptions:
    return schemas.KbOptions(
        kb_version=kb.version,
        genres=tuple(
            schemas.GenreOption(
                id=str(genre["id"]),
                label=str(genre["label"]),
                hybrid_friendly=tuple(genre.get("hybrid_friendly", ())),
            )
            for genre in kb.genres
        ),
        rating_systems=tuple(
            schemas.RatingSystemOption(
                id=str(system["id"]),
                label=str(system["label"]),
                territory=str(system["territory"]),
                classifications=tuple(
                    schemas.ClassificationOption(
                        id=str(classification["id"]),
                        label=str(classification["label"]),
                        min_audience_age=int(classification["min_audience_age"]),
                    )
                    # Ordered as the board orders them, not as JSON happened to
                    # store them: a rating picker listing R before PG is a
                    # picker nobody can scan.
                    for classification in sorted(
                        system["classifications"], key=lambda item: int(item["order"])
                    )
                ),
            )
            for system in kb.rating_systems
        ),
        budget_tiers=tuple(
            schemas.BudgetTierOption(
                id=str(tier["id"]),
                label=str(tier["label"]),
                order=int(tier["order"]),
                min_usd=int(tier["range_usd"]["min"]),
                max_usd=tier["range_usd"].get("max"),
                guild_context=str(tier["guild_context"]),
                # The scope is the point of choosing a tier. A picker showing
                # only dollar bands asks the writer to guess at the location
                # count and speaking cast they actually care about.
                scope=dict(tier["scope"]),
            )
            for tier in sorted(kb.budget_tiers, key=lambda item: int(item["order"]))
        ),
        territories=tuple(
            schemas.TerritoryOption(
                id=str(territory["id"]),
                label=str(territory["label"]),
                rating_system=str(territory["rating_system"]),
            )
            for territory in kb.territories
        ),
        archetypes=tuple(
            schemas.ArchetypeOption(
                id=str(archetype["id"]),
                label=str(archetype["label"]),
                description=str(archetype["premise"]),
                min_beats=int(archetype["min_beats"]),
            )
            for archetype in kb.archetypes
        ),
    )
