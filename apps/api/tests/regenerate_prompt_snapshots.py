"""Regenerate the committed prompt snapshots.

Deliberately a separate command rather than an auto-update on failure. A
snapshot that rewrites itself when it disagrees records nothing; the point is
that a prompt change shows up as a reviewable diff, since prompt wording moves
the output distribution and is therefore part of the experiment.

    uv run python -m tests.regenerate_prompt_snapshots
"""

from __future__ import annotations

from app.kb.loader import load_knowledge_base
from tests.test_prompt_builder import CASES, SNAPSHOTS, _render


def main() -> None:
    kb = load_knowledge_base()
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    for name in sorted(CASES):
        path = SNAPSHOTS / f"{name}.md"
        path.write_text(_render(kb, name), encoding="utf-8")
        print(f"wrote {path.relative_to(SNAPSHOTS.parent.parent)}")


if __name__ == "__main__":
    main()
