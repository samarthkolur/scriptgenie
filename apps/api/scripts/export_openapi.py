"""Write the OpenAPI document to ``apps/api/openapi.json``.

The document is committed, and that is the point. It is the contract between
two apps written in two languages, and the TypeScript types the web app builds
against are generated from it. Committing it means a pull request that changes
the API shows that change as a reviewable diff, rather than as a build that
starts failing somewhere else.

Two things make the output stable enough to diff:

* the settings are fixed here rather than read from the environment, so the
  document does not depend on which ``.env`` the person running it has;
* the JSON is sorted and indented, so a reordering inside FastAPI's own
  dictionaries does not appear as a change to the API.

Run via ``pnpm codegen``, never by hand. CI regenerates and fails on a diff.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def build() -> dict[str, object]:
    """The document, generated from a deterministic application.

    ``_env_file=None`` so a developer's local ``.env`` cannot leak a project
    URL or an environment name into a committed artefact, and ``app_env`` is
    pinned because production disables the OpenAPI route entirely.
    """
    settings = Settings(_env_file=None, app_env="development")
    document: dict[str, object] = create_app(settings).openapi()
    return document


def main() -> None:
    OUTPUT.write_text(
        json.dumps(build(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
