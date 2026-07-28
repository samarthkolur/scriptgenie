"""Shared domain vocabulary.

Every enum here mirrors a definition in ``packages/constraint-kb/schema``. The
knowledge base stays the source of truth; these exist so Python cannot build a
value the knowledge base would reject, and so a typo becomes a validation error
at the boundary rather than a rule that silently never fires.

Because the vocabulary is duplicated, it is also pinned: ``test_domain_enums``
reads the schema files and asserts member-for-member equality. If someone adds
a rating dimension to the knowledge base and not to this module, that test
fails rather than the engine quietly ignoring the new axis.

Two kinds of ordering appear here, and conflating them is the bug this module
is shaped to prevent. :class:`ContentLevel` is numeric, so ``>`` means what it
looks like. The string vocabularies are ordinal by *declaration position* --
``limited_digital`` outranks ``practical_only`` because of where it sits in the
list, not because of how it sorts alphabetically. Comparing those with ``<``
would silently give the alphabetical answer, so the operators are removed and
:attr:`OrdinalVocabulary.rank` is the only way to ask.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Never


class OrdinalVocabulary(StrEnum):
    """A string vocabulary whose declaration order carries meaning.

    Ordering operators are disabled rather than left to inherit ``str``'s
    alphabetical behaviour, which would be wrong in a way that produces no
    error and no wrong-looking output -- ``"limited_digital" < "none"`` is
    ``True`` alphabetically and ``False`` in every sense the domain cares
    about. Use :attr:`rank`.
    """

    @property
    def rank(self) -> int:
        """Position in the declared order, ascending from the most restrictive."""
        return tuple(type(self)).index(self)

    def _refuse(self, _other: object) -> Never:
        raise TypeError(
            f"{type(self).__name__} has no alphabetical order; "
            f"compare {type(self).__name__}.rank instead"
        )

    __lt__ = _refuse
    __le__ = _refuse
    __gt__ = _refuse
    __ge__ = _refuse


class ContentDimension(StrEnum):
    """The six axes on which genre demand and rating permission are both expressed.

    Sharing one scale between what a genre wants and what a board allows is
    what lets conflict detection be arithmetic rather than interpretive.
    """

    VIOLENCE = "violence"
    SEXUAL_CONTENT = "sexual_content"
    LANGUAGE = "language"
    THEMATIC_DARKNESS = "thematic_darkness"
    DRUG_USE = "drug_use"
    HORROR_INTENSITY = "horror_intensity"


class ContentLevel(IntEnum):
    """Ordinal content intensity, 0 none to 4 explicit.

    Numeric on purpose: ``dimension_exceeds`` is a subtraction. Comparable
    across rating systems only through the equivalence table, never directly,
    because boards apply different criteria to the same nominal level.
    """

    NONE = 0
    MILD = 1
    MODERATE = 2
    STRONG = 3
    EXPLICIT = 4


class Severity(StrEnum):
    """What a detected conflict is permitted to do to the user.

    Not ordinal: nothing compares severities by position, and the tiering is a
    policy about interruption rather than a scale. HARD blocks generation and
    is reserved for combinations no narrative can satisfy. SOFT proceeds after
    explicit acknowledgement. ADVISORY is informational. The split exists so a
    false positive never silently blocks an experienced writer.
    """

    HARD = "HARD"
    SOFT = "SOFT"
    ADVISORY = "ADVISORY"


class VfxComplexity(OrdinalVocabulary):
    """Visual effects a budget permits or a genre expects. Ascending permissiveness."""

    NONE = "none"
    PRACTICAL_ONLY = "practical_only"
    LIMITED_DIGITAL = "limited_digital"
    UNRESTRICTED = "unrestricted"


class PeriodSetting(OrdinalVocabulary):
    """When a story may be set. Ascending permissiveness.

    ``contemporary_or_recent`` means within roughly thirty years, where costume
    and set dressing stay inexpensive.
    """

    CONTEMPORARY_ONLY = "contemporary_only"
    CONTEMPORARY_OR_RECENT = "contemporary_or_recent"
    ANY_WITH_ALLOCATION = "any_with_allocation"
    ANY = "any"


class ActionComplexity(OrdinalVocabulary):
    """Staging a budget supports or a genre expects. Ascending permissiveness."""

    DIALOGUE_DRIVEN = "dialogue_driven"
    LIMITED_PRACTICAL = "limited_practical"
    MODERATE_SET_PIECES = "moderate_set_pieces"
    UNRESTRICTED = "unrestricted"


class NarrativeEconomy(StrEnum):
    """How hard each scene must work.

    Deliberately not an :class:`OrdinalVocabulary`: the only rule that reads it
    (``high_economy_with_large_cast_demand``) tests equality against ``high``.
    Nothing ranks these, so nothing here implies they can be ranked.
    """

    HIGH = "high"
    MODERATE = "moderate"
    STANDARD = "standard"
    RELAXED = "relaxed"


class LocationPressure(OrdinalVocabulary):
    """How many distinct locations an archetype's structure tends to require."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class ResolutionEffectKind(StrEnum):
    """What choosing a resolution does to the bundle.

    ``ACKNOWLEDGE_RELAXATION`` records the tension without moving any bound,
    which is why a resolution may legitimately leave the numbers unchanged.
    """

    CLAMP_DIMENSION_TO_PERMITTED = "clamp_dimension_to_permitted"
    ACKNOWLEDGE_RELAXATION = "acknowledge_relaxation"
    REQUIRES_BUNDLE_CHANGE = "requires_bundle_change"
