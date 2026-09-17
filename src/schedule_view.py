from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True)
class DeadlineThresholds:
    urgent_days: int = 3
    soon_days: int = 7

    def __post_init__(self) -> None:
        if self.urgent_days < 0 or self.soon_days < 0:
            raise ValueError("日数は0以上にしてください。")
        if self.urgent_days > self.soon_days:
            raise ValueError("urgent_daysはsoon_days以下にしてください。")


def classify_deadline(deadline: pd.Timestamp | None, today: date, thresholds: DeadlineThresholds) -> str:
    if deadline is None or pd.isna(deadline):
        return "unknown"
    remaining = (deadline.date() - today).days
    if remaining < 0:
        return "expired"
    if remaining <= thresholds.urgent_days:
        return "urgent"
    if remaining <= thresholds.soon_days:
        return "soon"
    return "normal"


def add_deadline_status(
    df: pd.DataFrame, thresholds: DeadlineThresholds, today: date | None = None
) -> pd.DataFrame:
    today = today or datetime.now().date()
    result = df.copy()
    result["deadline_status"] = result["deadline_date"].apply(
        lambda d: classify_deadline(d, today, thresholds)
    )
    return result
