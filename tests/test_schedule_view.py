from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.schedule_view import DeadlineThresholds, add_deadline_status, classify_deadline

_TODAY = date(2026, 7, 30)
_THRESHOLDS = DeadlineThresholds(urgent_days=3, soon_days=7)


def test_deadline_thresholds_invalid_order_raises() -> None:
    with pytest.raises(ValueError):
        DeadlineThresholds(urgent_days=10, soon_days=3)


def test_deadline_thresholds_negative_raises() -> None:
    with pytest.raises(ValueError):
        DeadlineThresholds(urgent_days=-1)


@pytest.mark.parametrize(
    ("deadline", "expected"),
    [
        (pd.Timestamp(2026, 7, 30), "urgent"),  # 当日
        (pd.Timestamp(2026, 8, 2), "urgent"),  # 3日後（境界）
        (pd.Timestamp(2026, 8, 3), "soon"),  # 4日後
        (pd.Timestamp(2026, 8, 6), "soon"),  # 7日後（境界）
        (pd.Timestamp(2026, 8, 7), "normal"),  # 8日後
        (pd.Timestamp(2026, 7, 29), "expired"),  # 前日
        (pd.NaT, "unknown"),
    ],
)
def test_classify_deadline_boundaries(deadline: pd.Timestamp, expected: str) -> None:
    assert classify_deadline(deadline, _TODAY, _THRESHOLDS) == expected


def test_add_deadline_status_adds_column() -> None:
    df = pd.DataFrame({"deadline_date": [pd.Timestamp(2026, 7, 30), pd.NaT]})
    result = add_deadline_status(df, _THRESHOLDS, today=_TODAY)
    assert result["deadline_status"].tolist() == ["urgent", "unknown"]
