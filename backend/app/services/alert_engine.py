"""
Alert engine — checks all active alert rules against the latest indicator values
and inserts new pattern_alerts when thresholds are crossed.
Run this after each data ingestion cycle.
"""
from sqlalchemy.orm import Session
from ..models import AlertRule, IndicatorValue, PatternAlert


def run_alert_check(db: Session, year: int) -> list[PatternAlert]:
    """Evaluate all active rules against indicator_values for the given year."""
    triggered: list[PatternAlert] = []
    rules = db.query(AlertRule).filter(AlertRule.is_active == True).all()

    for rule in rules:
        values = (
            db.query(IndicatorValue)
            .filter(
                IndicatorValue.indicator_id == rule.indicator_id,
                IndicatorValue.year == year,
                IndicatorValue.value.isnot(None),
            )
            .all()
        )

        for iv in values:
            if not _crosses_threshold(iv.value, rule.condition, rule.threshold):
                continue

            # Skip if we already have an active alert for this country+rule
            existing = (
                db.query(PatternAlert)
                .filter(
                    PatternAlert.country_id == iv.country_id,
                    PatternAlert.alert_rule_id == rule.id,
                    PatternAlert.is_active == True,
                )
                .first()
            )
            if existing:
                continue

            alert = PatternAlert(
                country_id=iv.country_id,
                alert_rule_id=rule.id,
                indicator_id=rule.indicator_id,
                trigger_value=float(iv.value),
                threshold=float(rule.threshold),
                severity=rule.severity,
                message=(
                    f"{iv.country_id}: {rule.name} — "
                    f"value {iv.value} {'>' if rule.condition == 'above' else '<'} "
                    f"threshold {rule.threshold} ({year})"
                ),
                is_active=True,
            )
            db.add(alert)
            triggered.append(alert)

    db.commit()
    return triggered


def _crosses_threshold(value: float, condition: str, threshold: float) -> bool:
    if condition == "above":
        return value > threshold
    if condition == "below":
        return value < threshold
    return False
