from __future__ import annotations

import io

import pandas as pd
import pytest

from src.csv_import import normalize_bids, read_njss_csv, validate_columns

_VALID_ROW = {
    "案件ID": "33725209",
    "案件名": "○○工事",
    "案件概要URL": "https://example.com/1",
    "機関": "防衛省(MOD) 航空自衛隊 入間基地",
    "履行/納品場所": "埼玉県\n航空自衛隊入間基地",
    "案件公示日": "2026/07/01",
    "入札日": "2026/08/20",
    "資料等提出日": "2026/08/05",
    "入札資格": "防衛省競争参加資格 建設・土木・工事系 C",
    "業種": "機械器具設置工事",
    "予定価格": "15,000,000",
}


def test_validate_columns_missing_raises() -> None:
    df = pd.DataFrame([{"案件名": "テスト"}])
    with pytest.raises(ValueError):
        validate_columns(df)


def test_normalize_bids_converts_dates_and_price() -> None:
    df = pd.DataFrame([_VALID_ROW])
    result = normalize_bids(df)

    assert result.loc[0, "estimated_price_jpy"] == 15_000_000
    assert isinstance(result.loc[0, "deadline_date"], pd.Timestamp)
    assert result.loc[0, "title"] == "○○工事"


def test_normalize_bids_keeps_undisclosed_price_as_nan() -> None:
    row = dict(_VALID_ROW, **{"予定価格": "非公表"})
    df = pd.DataFrame([row])
    result = normalize_bids(df)

    assert pd.isna(result.loc[0, "estimated_price_jpy"])


def test_normalize_bids_uses_submission_date_as_deadline() -> None:
    df = pd.DataFrame([_VALID_ROW])
    result = normalize_bids(df)

    assert result.loc[0, "deadline_date"] == pd.Timestamp("2026-08-05")


def test_normalize_bids_falls_back_to_bid_date_when_submission_date_missing() -> None:
    row = dict(_VALID_ROW, **{"資料等提出日": ""})
    df = pd.DataFrame([row])
    result = normalize_bids(df)

    assert result.loc[0, "deadline_date"] == pd.Timestamp("2026-08-20")


def test_read_njss_csv_reads_utf8_sig() -> None:
    csv_text = pd.DataFrame([_VALID_ROW]).to_csv(index=False)
    df = read_njss_csv(io.BytesIO(csv_text.encode("utf-8-sig")))
    assert df.loc[0, "案件名"] == "○○工事"


def test_read_njss_csv_falls_back_to_cp932() -> None:
    csv_text = pd.DataFrame([_VALID_ROW]).to_csv(index=False)
    df = read_njss_csv(io.BytesIO(csv_text.encode("cp932")))
    assert df.loc[0, "案件名"] == "○○工事"
