from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final

import pandas as pd

DEFAULT_SETTINGS_PATH: Final[Path] = Path("config/filter_settings.json")


@dataclass(frozen=True)
class FilterSettings:
    target_industries: tuple[str, ...] = ()
    target_organizations: tuple[str, ...] = ()
    unified_qualification_keywords: tuple[str, ...] = ()
    min_estimated_price_jpy: int = 0
    max_estimated_price_jpy: int | None = None
    qualification_expiry_date: str | None = None

    def __post_init__(self) -> None:
        if self.min_estimated_price_jpy < 0:
            raise ValueError("min_estimated_price_jpyは0以上にしてください。")
        if (
            self.max_estimated_price_jpy is not None
            and self.max_estimated_price_jpy < self.min_estimated_price_jpy
        ):
            raise ValueError("max_estimated_price_jpyはmin_estimated_price_jpy以上にしてください。")
        if self.qualification_expiry_date is not None:
            datetime.strptime(self.qualification_expiry_date, "%Y-%m-%d")


def load_filter_settings(path: Path = DEFAULT_SETTINGS_PATH) -> FilterSettings:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return FilterSettings(
        target_industries=tuple(data.get("target_industries", [])),
        target_organizations=tuple(data.get("target_organizations", [])),
        unified_qualification_keywords=tuple(data.get("unified_qualification_keywords", [])),
        min_estimated_price_jpy=int(data.get("min_estimated_price_jpy", 0)),
        max_estimated_price_jpy=data.get("max_estimated_price_jpy"),
        qualification_expiry_date=data.get("qualification_expiry_date"),
    )


def _contains_any(series: pd.Series, keywords: tuple[str, ...]) -> pd.Series:
    if not keywords:
        return pd.Series(False, index=series.index)
    pattern = "|".join(re.escape(keyword) for keyword in keywords)
    return series.fillna("").str.contains(pattern, regex=True)


def _industry_cell_matches(cell: object, keywords: tuple[str, ...]) -> bool:
    """NJSSの「業種」列（改行区切りの複数カテゴリ）と、資格審査結果通知書の業種名
    （「工事」抜きの表記）を突き合わせる。単純な部分一致は「管」が「指定管理」に、
    「大工」が「大工道具」に誤一致するなど短いキーワードで誤検出するため、
    カテゴリ単位（改行区切り）・トークン単位（「・」区切り）の完全一致で判定する。
    """
    if pd.isna(cell):
        return False
    segments = [s.strip() for s in str(cell).split("\n") if s.strip()]
    for keyword in keywords:
        full_name = f"{keyword}工事"
        if "・" in keyword:
            # 「とび・土工・コンクリート」のような複合名は、カテゴリ全体との完全一致で判定する
            # （細分割すると複合名自体が壊れてしまうため）。
            if any(segment == full_name for segment in segments):
                return True
        else:
            for segment in segments:
                tokens = [t.strip() for t in segment.split("・") if t.strip()]
                if keyword in tokens or full_name in tokens:
                    return True
    return False


def _industry_matches(series: pd.Series, keywords: tuple[str, ...]) -> pd.Series:
    if not keywords:
        return pd.Series(False, index=series.index)
    return series.apply(lambda cell: _industry_cell_matches(cell, keywords))


def filter_bids(df: pd.DataFrame, settings: FilterSettings, today: date | None = None) -> pd.DataFrame:
    today = today or datetime.now().date()
    result = df.copy()

    # 「業種」は実際のCSVでは複数値・改行区切り、かつ資格審査結果通知書の表記
    # （例:「舗装」）とNJSS側の表記（例:「舗装工事」）が完全一致しないため、
    # カテゴリ・トークン単位の完全一致で判定する（単純な部分一致は誤検出するため使わない）。
    industry_ok = _industry_matches(result["industry"], settings.target_industries)

    # 建設業種の資格に加えて、全省庁統一資格などを要求する役務案件も候補に含める
    # （「入札資格」列の生テキストに対する部分一致。等級までは判定しない＝人間確認が必要）。
    unified_ok = _contains_any(result["qualification_requirement"], settings.unified_qualification_keywords)

    qualified_ok = industry_ok | unified_ok

    if settings.target_organizations:
        # 発注機関名は表記ゆれがあるため、完全一致ではなく部分一致(OR)で判定する。
        org_ok = _contains_any(result["organization"], settings.target_organizations)
    else:
        org_ok = pd.Series(True, index=result.index)

    price = result["estimated_price_jpy"]
    within_min = price >= settings.min_estimated_price_jpy
    if settings.max_estimated_price_jpy is not None:
        within_max = price <= settings.max_estimated_price_jpy
    else:
        within_max = pd.Series(True, index=result.index)
    # 予定価格が非公表(NaN)の案件は自動除外せず候補に残し、UI側で要確認扱いにする。
    price_ok = price.isna() | (within_min & within_max)

    expiry_date = (
        datetime.strptime(settings.qualification_expiry_date, "%Y-%m-%d").date()
        if settings.qualification_expiry_date
        else None
    )
    qualification_expired = expiry_date is not None and today > expiry_date
    result["qualification_expired"] = qualification_expired

    if qualification_expired:
        result["is_candidate"] = False
    else:
        result["is_candidate"] = qualified_ok & org_ok & price_ok

    return result.sort_values(
        ["is_candidate", "deadline_date"], ascending=[False, True]
    ).reset_index(drop=True)
