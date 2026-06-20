"""Shared gherkin 29.x syntax lint gate (GEN-03 / D-04).

ONE linter for BOTH generation AND edit/approve (D-04) — generation.py re-imports
`validate_gherkin` from here so there is a single Parser usage. This is the Phase-3
`generation.validate_gherkin` moved VERBATIM into the gates package.

CRITICAL: gherkin-official is 29.x TRANSITIVE via pytest-bdd 8.1 (which hard-pins
gherkin-official>=29,<30). A direct gherkin-official==40.* pin is INCOMPATIBLE (the carried
gherkin-pytest-bdd-conflict). `from gherkin.parser import Parser` imports the SAME parser
pytest-bdd executes — do NOT add a gherkin-official pin to pyproject.toml.
"""

from gherkin.parser import Parser


class GenerationError(Exception):
    """Raised when generation/validation fails (malformed Gherkin, vacuous assertions, etc.).

    On a Gherkin validation failure NO .feature/draft is written — the write happens only AFTER
    the parser accepts the text (T-03-12). Shared across the lint gate, the assertion gate, and
    generation.py so generation and the edit/approve router raise ONE exception type.
    """


def validate_gherkin(text: str) -> None:
    """Validate Gherkin with gherkin 29.x's Parser BEFORE persisting (T-03-12).

    `Parser().parse(...)` raises (CompositeParserException / token errors) on malformed input.
    We wrap any parser failure as GenerationError so the caller can decide WITHOUT a row/file
    ever being written.
    """
    try:
        Parser().parse(text)
    except Exception as exc:  # noqa: BLE001 -- any parse failure => reject before write
        raise GenerationError(f"invalid Gherkin: {exc}") from exc
