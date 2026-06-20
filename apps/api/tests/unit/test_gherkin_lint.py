"""Unit: the shared gherkin 29.x lint gate (GEN-03 / D-04). No keys, no neo4j."""

import pytest

from app.services.gates.gherkin_lint import GenerationError, validate_gherkin

_VALID_FEATURE = """Feature: Login
  Scenario: Standard user logs in
    Given the login page
    When a standard user logs in
    Then the inventory page is shown
"""


def test_valid_gherkin_parses_without_error():
    # A well-formed Feature/Scenario must not raise.
    validate_gherkin(_VALID_FEATURE)


def test_malformed_gherkin_raises_generation_error():
    with pytest.raises(GenerationError):
        validate_gherkin("not gherkin {{{")


def test_generation_reexports_the_shared_validator():
    # D-04: generation.py shares the ONE linter (re-import, no duplicate Parser logic).
    from app.services import generation

    assert generation.validate_gherkin is validate_gherkin
    assert generation.GenerationError is GenerationError
