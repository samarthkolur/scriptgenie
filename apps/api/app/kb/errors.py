"""Knowledge base error types.

Loading failures are fatal and must be specific. A knowledge base that is
silently wrong produces conflict reports that are confidently wrong, which is
worse than a service that refuses to start.
"""

from __future__ import annotations


class KnowledgeBaseError(Exception):
    """Base class for every knowledge base failure."""


class KnowledgeBaseFileError(KnowledgeBaseError):
    """A data or schema file is missing or is not readable as JSON."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


class KnowledgeBaseValidationError(KnowledgeBaseError):
    """A data file does not satisfy its schema.

    Carries the JSON pointer of the offending value so the fix is obvious
    without re-running a validator by hand.
    """

    def __init__(self, path: str, pointer: str, message: str) -> None:
        self.path = path
        self.pointer = pointer
        self.message = message
        location = pointer or "<root>"
        super().__init__(f"{path} at {location}: {message}")


class KnowledgeBaseIntegrityError(KnowledgeBaseError):
    """The files are individually valid but inconsistent with each other.

    Cross-file references — a territory naming a rating system, an archetype
    scoring a genre — are not expressible in JSON Schema, so they are checked
    separately and reported here.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
