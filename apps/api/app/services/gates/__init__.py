"""Quality gates for generated scenarios (GEN-03 / D-03 / D-04).

Two deterministic gates, both enforced at generation AND on edit/approve:
  - gherkin_lint.validate_gherkin — gherkin 29.x syntax lint (the parser pytest-bdd uses).
  - assertion_gate.resolve_then_refs / assert_non_vacuous — the structured Then→KG
    no-vacuous-assertion gate (the novel deterministic trust mechanism).
"""
