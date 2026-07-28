"""Domain models for the constraint, scope and variant layers.

Import from ``app.domain`` rather than from the modules beneath it. The split
into ``enums``, ``constraints``, ``conflicts`` and ``variants`` is for reading,
not for addressing, and keeping the import surface flat means moving a model
between those files stays a refactor rather than a breaking change.

No model here calls a language model, reads the knowledge base, or performs
I/O. They are the vocabulary the deterministic engines in Phase 2 speak.
"""

from __future__ import annotations

from app.domain.conflicts import (
    Conflict,
    ConflictReport,
    ResolutionChoice,
    ResolutionDelta,
    ResolutionEffect,
    ResolutionOption,
    ResolvedBundle,
)
from app.domain.constraints import (
    AudienceSelection,
    BudgetTier,
    ConstraintBundle,
    ContentThresholds,
    DomainModel,
    GenreSelection,
    Identifier,
    RatingTarget,
    ScopeEnvelope,
    TerritorySet,
)
from app.domain.enums import (
    ActionComplexity,
    ContentDimension,
    ContentLevel,
    LocationPressure,
    NarrativeEconomy,
    OrdinalVocabulary,
    PeriodSetting,
    ResolutionEffectKind,
    Severity,
    VfxComplexity,
)
from app.domain.variants import (
    ArchetypeAssignment,
    ConstraintSatisfactionReport,
    DimensionCheck,
    PlotBeat,
    PlotVariant,
    ScopeCheck,
    VerificationResult,
)

__all__ = [
    "ActionComplexity",
    "ArchetypeAssignment",
    "AudienceSelection",
    "BudgetTier",
    "Conflict",
    "ConflictReport",
    "ConstraintBundle",
    "ConstraintSatisfactionReport",
    "ContentDimension",
    "ContentLevel",
    "ContentThresholds",
    "DimensionCheck",
    "DomainModel",
    "GenreSelection",
    "Identifier",
    "LocationPressure",
    "NarrativeEconomy",
    "OrdinalVocabulary",
    "PeriodSetting",
    "PlotBeat",
    "PlotVariant",
    "RatingTarget",
    "ResolutionChoice",
    "ResolutionDelta",
    "ResolutionEffect",
    "ResolutionEffectKind",
    "ResolutionOption",
    "ResolvedBundle",
    "ScopeCheck",
    "ScopeEnvelope",
    "Severity",
    "TerritorySet",
    "VerificationResult",
    "VfxComplexity",
]
