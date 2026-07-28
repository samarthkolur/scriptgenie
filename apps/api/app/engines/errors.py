"""Engine error types.

Separate from :mod:`app.kb.errors` because these describe a failure to reason
about a valid knowledge base, not a failure to load one. The distinction
matters operationally: a knowledge base error means the service should not have
started, while an engine error means this request cannot be answered.
"""

from __future__ import annotations


class EngineError(Exception):
    """Base class for every deterministic engine failure."""


class ConflictDetectionError(EngineError):
    """A rule could not be evaluated or rendered against this bundle.

    Raised rather than skipped. A rule that silently fails to evaluate is a
    conflict that silently does not exist, and a missing conflict is the exact
    failure this system was built to prevent.
    """


class UnknownReferenceError(EngineError):
    """A bundle names a knowledge base row that does not exist.

    The domain models validate identifier *shape*, which cannot know whether
    ``horrror`` is a real genre. This is where that is caught.
    """

    def __init__(self, kind: str, identifier: str) -> None:
        self.kind = kind
        self.identifier = identifier
        super().__init__(f"bundle references unknown {kind} '{identifier}'")


class UnresolvedHardConflictError(EngineError):
    """Resolutions were applied but a HARD conflict survived them.

    Carries the surviving rule ids so the caller can say which tensions are
    still blocking rather than only that something is.
    """

    def __init__(self, rule_ids: tuple[str, ...]) -> None:
        self.rule_ids = rule_ids
        listed = ", ".join(rule_ids)
        super().__init__(f"HARD conflicts remain after applying resolutions: {listed}")
