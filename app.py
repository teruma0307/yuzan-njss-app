from __future__ import annotations

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.bid_filter import FilterSettings, filter_bids, load_filter_settings
from src.csv_import import REQUIRED_COLUMNS, normalize_bids, read_njss_csv
from src.schedule_view import DeadlineThresholds, add_deadline_status

load_dotenv()

st.set_page_config(page_title="雄山 NJSS入札案件抽出MVP", page_icon="📋", layout="wide")

_STATUS_LABELS = {
    "urgent": "🔴 締切間近",
    "soon": "🟡 締切近め",
    "normal": "🟢 通常",
    "expired": "⚫ 締切超過",
    "unknown": "⚪ 非公表・要確認",
}

st.title("雄山 NJSS入札案件抽出MVP")
st.caption(
    "NJSSからエクスポートした案件CSVを読み込み、株式会社雄山が資格を持つ防衛省発注案件を抽出し、"
    "締切が近い案件を可視化します。"
)

try:
    default_settings = load_filter_settings()
except FileNotFoundError:
    default_settings = FilterSettings()

with st.sidebar:
    st.header("抽出条件")
    all_industries = list(default_settings.target_industries)
    target_industries = st.multiselect("資格のある業種", options=all_industries, default=all_industries)

    org_text = st.text_input(
        "発注機関キーワード（部分一致、複数はカンマ区切り）",
        value=", ".join(default_settings.target_organizations),
    )
    target_organizations = tuple(k.strip() for k in org_text.split(",") if k.strip())

    min_price = st.number_input(
        "予定価格 下限（円）", min_value=0, value=default_settings.min_estimated_price_jpy, step=100000
    )
    use_max_price = st.checkbox("予定価格の上限を設定する", value=default_settings.max_estimated_price_jpy is not None)
    max_price = None
    if use_max_price:
        max_price = st.number_input(
            "予定価格 上限（円）",
            min_value=0,
            value=default_settings.max_estimated_price_jpy or 0,
            step=100000,
        )

    st.header("締切ハイライト")
    urgent_days = st.number_input("締切間近とみなす日数", min_value=0, value=3, step=1)
    soon_days = st.number_input("締切近めとみなす日数", min_value=0, value=7, step=1)

try:
    filter_settings = FilterSettings(
        target_industries=tuple(target_industries),
        target_organizations=target_organizations,
        unified_qualification_keywords=default_settings.unified_qualification_keywords,
        min_estimated_price_jpy=int(min_price),
        max_estimated_price_jpy=int(max_price) if max_price is not None else None,
        qualification_expiry_date=default_settings.qualification_expiry_date,
    )
    thresholds = DeadlineThresholds(urgent_days=int(urgent_days), soon_days=int(soon_days))
except ValueError as exc:
    st.error(f"抽出条件の設定が不正です: {exc}")
    st.stop()

uploaded = st.file_uploader("NJSS案件CSVを選択してください", type=["csv"])

if uploaded is None:
    st.info("まず `data/sample_bids.csv` をアップロードしてください（NJSSからエクスポートしたCSVを想定した仮サンプルです）。")
    st.code(", ".join(sorted(REQUIRED_COLUMNS)), language="text")
    st.stop()

try:
    raw_df = read_njss_csv(uploaded)
    normalized = normalize_bids(raw_df)
    filtered = filter_bids(normalized, filter_settings)
    result = add_deadline_status(filtered, thresholds)
except Exception as exc:
    st.error(f"CSVの読込または処理に失敗しました: {exc}")
    st.stop()

if bool(result["qualification_expired"].any()):
    st.error(
        f"雄山の資格有効期限（{filter_settings.qualification_expiry_date}）を過ぎているため、"
        "候補を表示していません。最新の資格審査結果通知書をご確認のうえ、設定を更新してください。"
    )

summary1, summary2, summary3 = st.columns(3)
summary1.metric("登録案件数", f"{len(result):,}")
summary2.metric("候補案件数", f"{int(result['is_candidate'].sum()):,}")
urgent_count = int((result["deadline_status"] == "urgent").sum())
summary3.metric("締切間近の件数", f"{urgent_count:,}")

st.subheader("候補案件")
st.info(
    "「入札資格」列の等級（ランク）は自動判定していません。案件ごとに必要な等級・区分は"
    "この列の生テキストと案件詳細URLで必ず人が確認してください。"
    "また「締切」は資料等提出日（無ければ入札日）を基準にした目安です。"
)
candidates = result[result["is_candidate"]].copy()

if candidates.empty:
    st.warning("現在の条件を満たす案件はありません。抽出条件を見直してください。")
else:
    candidates["approval"] = False
    candidates["deadline_status_label"] = candidates["deadline_status"].map(_STATUS_LABELS)
    edited = st.data_editor(
        candidates[
            [
                "approval",
                "deadline_status_label",
                "title",
                "organization",
                "region",
                "industry",
                "qualification_requirement",
                "estimated_price_jpy",
                "announce_date",
                "submission_date",
                "bid_date",
                "detail_url",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "approval": st.column_config.CheckboxColumn("応札検討として承認"),
            "deadline_status_label": st.column_config.TextColumn("締切状況"),
            "title": st.column_config.TextColumn("案件名"),
            "organization": st.column_config.TextColumn("発注機関"),
            "region": st.column_config.TextColumn("履行/納品場所"),
            "industry": st.column_config.TextColumn("業種"),
            "qualification_requirement": st.column_config.TextColumn("入札資格（要確認）"),
            "estimated_price_jpy": st.column_config.NumberColumn("予定価格", format="¥%d"),
            "announce_date": st.column_config.DateColumn("案件公示日"),
            "submission_date": st.column_config.DateColumn("資料等提出日"),
            "bid_date": st.column_config.DateColumn("入札日"),
            "detail_url": st.column_config.LinkColumn("案件詳細URL"),
        },
        key="candidate_editor",
    )

    approved = edited[edited["approval"]].copy()
    st.download_button(
        "承認済み案件CSVをダウンロード",
        approved.to_csv(index=False).encode("utf-8-sig"),
        file_name="approved_bids.csv",
        mime="text/csv",
        disabled=approved.empty,
    )

with st.expander("全案件（原文CSVの正規化後データ）"):
    st.dataframe(result, hide_index=True, use_container_width=True)

st.caption(
    "注意：この版は書類作成の自動化やSQLite保存を行いません。"
    "金額・資格要件はCSVの値をそのまま表示しており、AIによる推測・補完は行っていません。"
    "応札判断は必ず人間が最終確認してください。"
)
