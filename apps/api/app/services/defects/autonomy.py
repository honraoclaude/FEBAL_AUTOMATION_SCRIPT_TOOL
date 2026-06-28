"""The autonomous-filing gate (JIRA-02 / D-04) — a PURE structural flag-AND-threshold check.

This is the CORE safety property of the defect pipeline (T-09-12, elevation of privilege):
a real Jira ticket is filed WITHOUT a human ONLY when BOTH

  - settings.jira_autonomous_enabled is True   (the per-target flag, OFF by default — D-04), AND
  - conf >= settings.jira_confidence_threshold  (the QUAL-03-calibrated floor, Plan 02).

Flag OFF -> never files (even at conf 100). Below the calibrated threshold -> never files (even
flag-on). Both true -> MAY file. Until a human reviews accuracy (>=85%) + draft precision (>=90%)
and flips the config flag, EVERY classification stays a draft for human apply/reject.

PURITY: the function reads the SHIPPED settings (never a hardcoded literal — the heal_high_threshold
discipline) and the passed confidence; no I/O, no LLM, deterministic. Mirrors RESEARCH Pattern 6.
"""

from __future__ import annotations

from app.core.config import settings


def may_autofile(conf: int) -> bool:
    """True only when autonomy is ENABLED and `conf` is at/above the calibrated threshold.

    The threshold is `settings.jira_confidence_threshold` (calibrated by QUAL-03), never a
    literal. Flag-off returns False at any confidence; below-threshold returns False even
    when the flag is on. This is the only path by which a ticket files without a human.
    """
    return bool(
        settings.jira_autonomous_enabled and conf >= settings.jira_confidence_threshold
    )
