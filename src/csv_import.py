from __future__ import annotations

from typing import Any, Final

import pandas as pd

# 実際にユーザーから提供されたNJSS CSVエクスポート（2026-07-30受領）で確認した列名。
REQUIRED_COLUMNS: Final[set[str]] = {
    "案件ID",
    "案件名",
    "案件概要URL",
    "機関",
    "履行/納品場所",
    "案件公示日",
    "入札日",
    "資料等提出日",
    "入札資格",
    "業種",
    "予定価格",
}

COLUMN_RENAME_MAP: Final[dict[str, str]] = {
    "案件ID": "case_id",
    "案件名": "title",
    "案件概要URL": "detail_url",
    "機関": "organization",
    "履行/納品場所": "region",
    "案件公示日": "announce_date",
    "入札日": "bid_date",
    "資料等提出日": "submission_date",
    "入札資格": "qualification_requirement",
    "業種": "industry",
    "予定価格": "estimated_price_jpy",
}

DATE_COLUMNS: Final[list[str]] = ["announce_date", "bid_date", "submission_date"]


def read_njss_csv(file: Any) -> pd.DataFrame:
    try:
        return pd.read_csv(file, encoding="utf-8-sig")
    except UnicodeDecodeError:
        file.seek(0)
        return pd.read_csv(file, encoding="cp932")


def validate_columns(df: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"必須列が不足しています: {', '.join(sorted(missing))}")


def normalize_bids(df: pd.DataFrame) -> pd.DataFrame:
    validate_columns(df)
    result = df.rename(columns=COLUMN_RENAME_MAP).copy()

    for column in DATE_COLUMNS:
        result[column] = pd.to_datetime(result[column], errors="coerce")

    # 実際のCSVには「申込締切日」に相当する列がなく、資料等提出日が実質的な行動締切、
    # それが空欄の案件は入札日を代わりに使う（開札日相当の列も存在しないため）。
    result["deadline_date"] = result["submission_date"].fillna(result["bid_date"])

    # "非公表"等の数値化できない値はNaNのまま残す。金額を推測して埋めてはいけない。
    result["estimated_price_jpy"] = pd.to_numeric(
        result["estimated_price_jpy"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )

    return result
