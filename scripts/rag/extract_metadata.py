"""事例 dict からメタデータを自動抽出するモジュール.

`cima_cases.json` の元データは年・施設種別・仕様などを構造化フィールドとして
持たない。本モジュールは title / subTitle / ex / tag の文字列を解析して、
ChromaDB のメタデータ filter や SPEC_SEARCH/FILTER_SEARCH の絞り込みで使える
構造化情報を生成する。

抽出される項目:
- year: 最新の言及年（int）or None
- facility_types: 施設種別の集合（list[str]）
- primary_facility_type: 最優先の施設種別（str）
- indoor_outdoor: "indoor"|"outdoor"|"both"|None
- pitch_values: 言及されたピッチ値（mm 単位、文字列）の list
- has_pitch: bool
- has_4k / has_8k: bool
- proper_nouns: title から抽出した固有名詞候補（list[str]）
- searchable_text: 埋め込み生成用に整形した本文（str）
"""
from __future__ import annotations

import re
from typing import Any

from load_data import FACILITY_KEYWORDS

# facility_type の優先順位（より特定的なものを上に）
FACILITY_PRIORITY: list[str] = [
    "hotel", "school", "expo", "pavilion", "station", "museum",
    "hall", "showroom", "exhibition", "event", "store", "other",
]

# year 抽出: 2010-2030 を想定
_YEAR_RE = re.compile(r"(20[1-3]\d)年")

# ピッチ抽出: "P1.9" "1.9mm" "1.9ミリ" "1.9 mm" 等
_PITCH_RE = re.compile(
    r"(?:P|ピッチ\s*)?(\d+\.\d+)\s*(?:mm|ｍｍ|ミリ|㎜)|P(\d+\.\d+)\b",
    re.IGNORECASE,
)

# 屋内 / 屋外 判定
_INDOOR_KEYWORDS = ("屋内", "室内", "インドア")
_OUTDOOR_KEYWORDS = ("屋外", "室外", "野外", "アウトドア")

# 4K / 8K
_4K_RE = re.compile(r"\b4K\b|４Ｋ", re.IGNORECASE)
_8K_RE = re.compile(r"\b8K\b|８Ｋ", re.IGNORECASE)

# 固有名詞抽出（load_data.py と同じパターン）
_KATAKANA_RE = re.compile(r"[ァ-ヴー]{3,}")
_UPPER_RE = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}\b")


def extract_year(text: str) -> int | None:
    """ex / title から最新の言及年を抽出する.

    Args:
        text: 検索対象テキスト（通常は ex フィールド）。

    Returns:
        最新の年（int）。見つからなければ None。
    """
    years = [int(y) for y in _YEAR_RE.findall(text)]
    return max(years) if years else None


def extract_facility_types(title: str, subtitle: str = "") -> list[str]:
    """title と subTitle に含まれるキーワードから施設種別をすべて抽出する.

    Args:
        title: 事例タイトル。
        subtitle: サブタイトル（任意）。

    Returns:
        FACILITY_KEYWORDS のキーのうち、title/subTitle にマッチしたものすべて。
        マッチなしの場合 ["other"]。
    """
    text = title + " " + subtitle
    matched: list[str] = []
    for ftype, keywords in FACILITY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(ftype)

    if not matched:
        return ["other"]
    return matched


def primary_facility_type(facility_types: list[str]) -> str:
    """複数マッチした facility_types から最優先の1つを返す.

    Args:
        facility_types: extract_facility_types() の結果。

    Returns:
        FACILITY_PRIORITY 順で最初にマッチするもの。すべて未該当なら "other"。
    """
    for f in FACILITY_PRIORITY:
        if f in facility_types:
            return f
    return "other"


def extract_indoor_outdoor(text: str) -> str | None:
    """text から indoor / outdoor を判定する.

    Args:
        text: title + subTitle + ex の連結など。

    Returns:
        "indoor" / "outdoor" / "both" / None。
    """
    has_in = any(kw in text for kw in _INDOOR_KEYWORDS)
    has_out = any(kw in text for kw in _OUTDOOR_KEYWORDS)
    if has_in and has_out:
        return "both"
    if has_in:
        return "indoor"
    if has_out:
        return "outdoor"
    return None


def extract_pitch_values(text: str) -> list[str]:
    """text からピッチ値（mm単位）を抽出する.

    Args:
        text: ex 等。

    Returns:
        ピッチ数値文字列の list（例: ["1.9", "2.5"]）、重複除去。
    """
    found: list[str] = []
    for m in _PITCH_RE.finditer(text):
        val = m.group(1) or m.group(2)
        if val and val not in found:
            found.append(val)
    return found


def extract_proper_nouns(title: str) -> list[str]:
    """title から固有名詞候補（カタカナ3+/英大文字3+）を抽出する.

    Args:
        title: 事例タイトル。

    Returns:
        固有名詞文字列の list（出現順、重複除去）。
    """
    found: list[str] = []
    for m in _KATAKANA_RE.findall(title):
        if m not in found:
            found.append(m)
    for m in _UPPER_RE.findall(title):
        if m not in found:
            found.append(m)
    return found


def build_searchable_text(case: dict[str, Any]) -> str:
    """ChromaDB 埋め込み生成用に整形した本文を返す.

    multilingual-e5-small は `passage: ...` プレフィックスを要求する。

    Args:
        case: cima_cases.json の1事例。

    Returns:
        埋め込み対象の整形済みテキスト。
    """
    tags = " ".join(case.get("tag", []))
    parts = [
        case.get("title", ""),
        case.get("subTitle", ""),
        case.get("ex", ""),
        f"タグ: {tags}" if tags else "",
    ]
    body = "\n".join(p for p in parts if p)
    return f"passage: {body}"


def extract_metadata(case: dict[str, Any]) -> dict[str, Any]:
    """1件分の case からメタデータを自動抽出する.

    ChromaDB の metadata に格納する想定。list/dict は ChromaDB が直接保存
    できないため、list はパイプ区切り文字列、bool/int/str/None のみ。

    Args:
        case: cima_cases.json の1事例。

    Returns:
        以下のキーを持つ辞書:
            - id (int)
            - year (int|None)
            - facility_types_csv (str): ","区切り
            - primary_facility_type (str)
            - tags_csv (str): ","区切り
            - indoor_outdoor (str|None)
            - has_pitch (bool)
            - pitch_values_csv (str): ","区切り
            - has_4k (bool)
            - has_8k (bool)
            - proper_nouns_csv (str): ","区切り
    """
    title = case.get("title", "")
    subtitle = case.get("subTitle", "")
    ex = case.get("ex", "")
    full_text = title + " " + subtitle + " " + ex

    facility_types = extract_facility_types(title, subtitle)
    pitch_values = extract_pitch_values(ex)
    proper_nouns = extract_proper_nouns(title)

    return {
        "id": case["id"],
        "year": extract_year(ex) or extract_year(title),
        "facility_types_csv": ",".join(facility_types),
        "primary_facility_type": primary_facility_type(facility_types),
        "tags_csv": ",".join(case.get("tag", [])),
        "indoor_outdoor": extract_indoor_outdoor(full_text) or "",
        "has_pitch": bool(pitch_values),
        "pitch_values_csv": ",".join(pitch_values),
        "has_4k": bool(_4K_RE.search(full_text)),
        "has_8k": bool(_8K_RE.search(full_text)),
        "proper_nouns_csv": ",".join(proper_nouns),
    }


def extract_all_metadata(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """全 case のメタデータを抽出する.

    Args:
        cases: load_cases() の結果。

    Returns:
        各 case に対応する metadata dict の list。
    """
    return [extract_metadata(c) for c in cases]


if __name__ == "__main__":
    # 単体動作 + サマリ表示
    from collections import Counter

    from load_data import load_cases

    cases = load_cases()
    print(f"[extract_metadata] {len(cases)} 件処理中...")
    metas = extract_all_metadata(cases)

    # 統計
    year_counter = Counter(m["year"] for m in metas)
    facility_counter = Counter(m["primary_facility_type"] for m in metas)
    indoor_outdoor_counter = Counter(m["indoor_outdoor"] for m in metas)
    pitch_counter = sum(1 for m in metas if m["has_pitch"])
    k4_counter = sum(1 for m in metas if m["has_4k"])
    k8_counter = sum(1 for m in metas if m["has_8k"])

    print(f"\n=== 年の分布 ===")
    for y, n in sorted(year_counter.items(), key=lambda x: (x[0] is None, x[0] or 0)):
        print(f"  {y if y else '(なし)':>6}: {n} 件")

    print(f"\n=== primary_facility_type の分布 ===")
    for f, n in facility_counter.most_common():
        print(f"  {f:>12}: {n} 件")

    print(f"\n=== indoor_outdoor の分布 ===")
    for io, n in indoor_outdoor_counter.most_common():
        print(f"  {io or '(なし)':>10}: {n} 件")

    print(f"\n=== 仕様フラグ ===")
    print(f"  has_pitch:    {pitch_counter} 件")
    print(f"  has_4k:       {k4_counter} 件")
    print(f"  has_8k:       {k8_counter} 件")

    # 抽出されたピッチ値の集合
    all_pitches = set()
    for m in metas:
        for p in m["pitch_values_csv"].split(","):
            if p:
                all_pitches.add(p)
    print(f"\n=== 抽出された pitch_values（ユニーク） ===")
    print(f"  {sorted(all_pitches, key=lambda x: float(x))}")

    # サンプル：テストケース ID の抽出結果
    by_id = {c["id"]: c for c in cases}
    print(f"\n=== テストケース ID のメタデータ ===")
    for tid in [1, 105, 107, 113]:
        if tid in by_id:
            meta = next(m for m in metas if m["id"] == tid)
            print(f"\n  id={tid}: {by_id[tid]['title']}")
            for k, v in meta.items():
                if v not in ("", False, []):
                    print(f"    {k:25}: {v}")
