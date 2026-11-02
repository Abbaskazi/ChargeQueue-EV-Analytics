"""Transparent, provisional congestion classification rules."""

from __future__ import annotations

from typing import Any


THRESHOLD_NOTE = (
    "Provisional thresholds for this academic project: below 50% is low, "
    "50% to below 80% is moderate, and 80% or above is high; they are not scientifically validated."
)


def classify_congestion(ports_available: float, ports_occupied: float) -> dict[str, Any]:
    """Classify current operational utilization without using supplied utilization_rate."""

    denominator = float(ports_available) + float(ports_occupied)
    if denominator <= 0:
        return {
            "operational_utilization": None,
            "alert_level": "unknown",
            "alert_message": "Congestion cannot be classified because no operational ports are available.",
            "threshold_note": THRESHOLD_NOTE,
        }
    utilization = float(ports_occupied) / denominator
    if utilization < 0.50:
        level = "low"
        message = "Low congestion based on current operational utilization."
    elif utilization < 0.80:
        level = "moderate"
        message = "Moderate congestion based on current operational utilization."
    else:
        level = "high"
        message = "High congestion based on current operational utilization."
    return {
        "operational_utilization": utilization,
        "alert_level": level,
        "alert_message": message,
        "threshold_note": THRESHOLD_NOTE,
    }
