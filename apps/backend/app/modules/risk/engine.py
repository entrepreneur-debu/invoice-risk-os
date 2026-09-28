"""Runs the deterministic rules and combines signals into a score and risk level.

Scoring is deterministic and documented: HIGH=40, MEDIUM=15, LOW=5, INFO=0, capped at 100.
Level: HIGH if any high signal or score >= 60; MEDIUM if any medium or score >= 25;
LOW if any low; otherwise NONE. AI observations never contribute to score or level.
"""

import logging
from dataclasses import dataclass

from app.models.enums import RiskLevel, Severity
from app.modules.risk.facts import RiskContext
from app.modules.risk.rules import ALL_RULES, Evidence, Rule, SignalDraft

logger = logging.getLogger(__name__)

ENGINE_VERSION = "1.0.0"
SEVERITY_WEIGHTS = {Severity.HIGH: 40, Severity.MEDIUM: 15, Severity.LOW: 5, Severity.INFO: 0}


@dataclass(frozen=True)
class EngineResult:
    signals: tuple[SignalDraft, ...]
    score: int
    level: RiskLevel
    rules_evaluated: int
    rules_failed: tuple[str, ...]


def score_signals(signals: tuple[SignalDraft, ...] | list[SignalDraft]) -> tuple[int, RiskLevel]:
    score = min(100, sum(SEVERITY_WEIGHTS[s.severity] for s in signals))
    severities = {s.severity for s in signals}
    if Severity.HIGH in severities or score >= 60:
        return score, RiskLevel.HIGH
    if Severity.MEDIUM in severities or score >= 25:
        return score, RiskLevel.MEDIUM
    if Severity.LOW in severities:
        return score, RiskLevel.LOW
    return score, RiskLevel.NONE


def run_rules(ctx: RiskContext, rules: tuple[Rule, ...] = ALL_RULES) -> EngineResult:
    signals: list[SignalDraft] = []
    failed: list[str] = []
    for rule in rules:
        try:
            signals.extend(rule.evaluate(ctx))
        except Exception:
            # A defective rule must not silently pass an invoice: record it visibly.
            logger.exception("risk rule failed", extra={"rule": rule.code})
            failed.append(rule.code)
            signals.append(
                SignalDraft(
                    "rule_evaluation_error",
                    "system",
                    Severity.MEDIUM,
                    "A risk check could not be completed",
                    "An internal error prevented one risk rule from running. Review manually.",
                    (Evidence("Rule", rule.code, "policy"),),
                )
            )
    score, level = score_signals(signals)
    return EngineResult(tuple(signals), score, level, len(rules), tuple(failed))
