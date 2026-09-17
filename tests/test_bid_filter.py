from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.bid_filter import FilterSettings, filter_bids, load_filter_settings


def _bids_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "title": "機械設備工事案件",
                "organization": "○○市役所",
                "industry": "機械器具設置工事",
                "qualification_requirement": "",
                "estimated_price_jpy": 15_000_000,
                "deadline_date": pd.Timestamp("2026-08-05"),
            },
            {
                "title": "対象外の業種",
                "organization": "○○市役所",
                "industry": "土木工事",
                "qualification_requirement": "",
                "estimated_price_jpy": 15_000_000,
                "deadline_date": pd.Timestamp("2026-08-05"),
            },
            {
                "title": "予定価格が低すぎる",
                "organization": "○○市役所",
                "industry": "機械器具設置工事",
                "qualification_requirement": "",
                "estimated_price_jpy": 100,
                "deadline_date": pd.Timestamp("2026-08-05"),
            },
            {
                "title": "予定価格が非公表",
                "organization": "○○市役所",
                "industry": "機械器具設置工事",
                "qualification_requirement": "",
                "estimated_price_jpy": float("nan"),
                "deadline_date": pd.Timestamp("2026-08-05"),
            },
        ]
    )


def _organization_bids_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "title": "防衛省の舗装工事",
                "organization": "防衛省近畿中部防衛局",
                "industry": "舗装工事",
                "qualification_requirement": "防衛省競争参加資格 建設・土木・工事系 C",
                "estimated_price_jpy": 12_000_000,
                "deadline_date": pd.Timestamp("2026-08-10"),
            },
            {
                "title": "市役所の舗装工事",
                "organization": "○○市役所",
                "industry": "舗装工事",
                "qualification_requirement": "",
                "estimated_price_jpy": 12_000_000,
                "deadline_date": pd.Timestamp("2026-08-10"),
            },
        ]
    )


def test_filter_settings_invalid_range_raises() -> None:
    with pytest.raises(ValueError):
        FilterSettings(min_estimated_price_jpy=100, max_estimated_price_jpy=50)


def test_filter_settings_negative_min_raises() -> None:
    with pytest.raises(ValueError):
        FilterSettings(min_estimated_price_jpy=-1)


def test_filter_bids_matches_industry_by_substring() -> None:
    # 資格審査結果通知書の表記「機械器具設置」とNJSSの表記「機械器具設置工事」は
    # 完全一致しないため、部分一致で拾えることを確認する。
    settings = FilterSettings(
        target_industries=("機械器具設置",),
        min_estimated_price_jpy=1_000_000,
    )
    result = filter_bids(_bids_df(), settings)

    candidates = result[result["is_candidate"]]["title"].tolist()
    assert "機械設備工事案件" in candidates
    assert "対象外の業種" not in candidates
    assert "予定価格が低すぎる" not in candidates


def test_filter_bids_keeps_undisclosed_price_as_candidate() -> None:
    settings = FilterSettings(
        target_industries=("機械器具設置",),
        min_estimated_price_jpy=1_000_000,
    )
    result = filter_bids(_bids_df(), settings)

    row = result[result["title"] == "予定価格が非公表"].iloc[0]
    assert bool(row["is_candidate"]) is True


def test_load_filter_settings_reads_json(tmp_path: Path) -> None:
    settings_path = tmp_path / "filter_settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "target_industries": ["舗装"],
                "target_organizations": ["防衛省"],
                "unified_qualification_keywords": ["全省庁統一資格"],
                "min_estimated_price_jpy": 500000,
                "max_estimated_price_jpy": 10000000,
            }
        ),
        encoding="utf-8",
    )

    settings = load_filter_settings(settings_path)

    assert settings.target_industries == ("舗装",)
    assert settings.target_organizations == ("防衛省",)
    assert settings.unified_qualification_keywords == ("全省庁統一資格",)
    assert settings.min_estimated_price_jpy == 500000
    assert settings.max_estimated_price_jpy == 10000000


def test_filter_bids_matches_organization_keyword() -> None:
    settings = FilterSettings(target_organizations=("防衛省",), target_industries=("舗装",))
    result = filter_bids(_organization_bids_df(), settings)

    candidates = result[result["is_candidate"]]["title"].tolist()
    assert "防衛省の舗装工事" in candidates


def test_filter_bids_excludes_unmatched_organization() -> None:
    settings = FilterSettings(target_organizations=("防衛省",), target_industries=("舗装",))
    result = filter_bids(_organization_bids_df(), settings)

    candidates = result[result["is_candidate"]]["title"].tolist()
    assert "市役所の舗装工事" not in candidates


def test_filter_bids_matches_unified_qualification_even_when_industry_unmatched() -> None:
    # 業種は資格対象外でも、入札資格に全省庁統一資格が含まれる役務案件は候補に含める。
    df = pd.DataFrame(
        [
            {
                "title": "防衛省の役務案件",
                "organization": "防衛省東北防衛局",
                "industry": "貨物運送",
                "qualification_requirement": "全省庁統一資格 役務の提供系 A\nB\nC\nD",
                "estimated_price_jpy": float("nan"),
                "deadline_date": pd.Timestamp("2026-08-10"),
            }
        ]
    )
    settings = FilterSettings(
        target_organizations=("防衛省",),
        target_industries=("舗装",),
        unified_qualification_keywords=("全省庁統一資格",),
    )
    result = filter_bids(df, settings)

    assert bool(result.loc[0, "is_candidate"]) is True


def test_filter_bids_forces_false_when_qualification_expired() -> None:
    settings = FilterSettings(
        target_organizations=("防衛省",),
        target_industries=("舗装",),
        qualification_expiry_date="2027-03-31",
    )
    result = filter_bids(_organization_bids_df(), settings, today=date(2027, 4, 1))

    assert bool(result["is_candidate"].any()) is False
    assert result["qualification_expired"].all()


def test_filter_bids_does_not_false_positive_on_short_keywords() -> None:
    # 実際のNJSS CSVで発見した誤検出パターン:「管」が「指定管理」に、
    # 「大工」が「大工道具」に部分一致してしまう問題の回帰テスト。
    df = pd.DataFrame(
        [
            {
                "title": "施設管理業務（無資格対象）",
                "organization": "防衛省東北防衛局",
                "industry": "建物・指定管理\n消防・防災関連",
                "qualification_requirement": "",
                "estimated_price_jpy": float("nan"),
                "deadline_date": pd.Timestamp("2026-08-10"),
            },
            {
                "title": "大工道具の物品調達（無資格対象）",
                "organization": "防衛省東北防衛局",
                "industry": "建設関連物品・大工道具・プレハブ",
                "qualification_requirement": "",
                "estimated_price_jpy": float("nan"),
                "deadline_date": pd.Timestamp("2026-08-10"),
            },
            {
                "title": "配管設備工事（有資格対象）",
                "organization": "防衛省東北防衛局",
                "industry": "管・空調・衛生工事",
                "qualification_requirement": "",
                "estimated_price_jpy": float("nan"),
                "deadline_date": pd.Timestamp("2026-08-10"),
            },
            {
                "title": "とび土工工事（有資格対象）",
                "organization": "防衛省東北防衛局",
                "industry": "とび・土工・コンクリート工事",
                "qualification_requirement": "",
                "estimated_price_jpy": float("nan"),
                "deadline_date": pd.Timestamp("2026-08-10"),
            },
        ]
    )
    settings = FilterSettings(
        target_organizations=("防衛省",),
        target_industries=("管", "大工", "とび・土工・コンクリート"),
    )
    result = filter_bids(df, settings)

    candidates = result[result["is_candidate"]]["title"].tolist()
    assert "施設管理業務（無資格対象）" not in candidates
    assert "大工道具の物品調達（無資格対象）" not in candidates
    assert "配管設備工事（有資格対象）" in candidates
    assert "とび土工工事（有資格対象）" in candidates


def test_filter_bids_ignores_expiry_when_not_set() -> None:
    settings = FilterSettings(
        target_industries=("機械器具設置",),
        min_estimated_price_jpy=1_000_000,
    )
    result = filter_bids(_bids_df(), settings, today=date(2099, 1, 1))

    candidates = result[result["is_candidate"]]["title"].tolist()
    assert "機械設備工事案件" in candidates
    assert not result["qualification_expired"].any()
