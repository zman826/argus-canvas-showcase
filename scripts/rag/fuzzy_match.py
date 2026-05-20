"""固有名詞ファジーマッチ（Layer 3: 検索側）.

DIRECT_RECALL インテントで、Whisper 誤認識 → Layer 2 補正でも完全一致しなかった
固有名詞クエリを、各 case のタイトル固有名詞集と Levenshtein 距離で照合する。

例:
    クエリ: "ガナホテル"（Layer 2 で補正されなかった想定）
    照合: 全 case の title 固有名詞集
    最良マッチ: id=113「ガーナーホテル大阪本町駅」の "ガーナーホテル" (distance=2)

Layer 2 (normalize_transcription.py) との違い:
    Layer 2: ASR テキスト中の固有名詞「断片」を語彙ベースで補正
    Layer 3: 補正後のクエリ全体（または entity）を、ケース ID にマッピング
"""
from __future__ import annotations

from typing import Any

try:
    import Levenshtein
except ImportError:
    Levenshtein = None  # type: ignore

from normalize_transcription import _levenshtein_distance

# DIRECT_RECALL 用のデフォルト閾値
DEFAULT_MAX_DISTANCE: int = 2
DEFAULT_MAX_RATIO: float = 0.34


def fuzzy_match_cases(
    query: str,
    cases_proper_nouns: dict[int, list[str]],
    max_distance: int = DEFAULT_MAX_DISTANCE,
    max_ratio: float = DEFAULT_MAX_RATIO,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """クエリと各 case の固有名詞集を Levenshtein 距離で照合する.

    Args:
        query: 検索クエリ（通常は entity の client_name や term）。
        cases_proper_nouns: {case_id: [proper_noun1, ...]} の dict
            （load_data.build_vocabulary() の "title_proper_nouns" を渡す想定）。
        max_distance: 許容する最大編集距離。
        max_ratio: 許容する distance/max_len 比。
        top_k: 上位何件返すか。

    Returns:
        マッチした case のリスト。各要素:
            {
                "id": int,
                "matched_term": str,        # ヒットした case 側の固有名詞
                "distance": int,
                "ratio": float,
            }
        距離昇順、上位 top_k 件まで。マッチなしなら空リスト。
    """
    if not query:
        return []

    candidates: list[dict[str, Any]] = []
    for cid, proper_nouns in cases_proper_nouns.items():
        # case 内のベストマッチ proper noun を選ぶ
        best_term: str | None = None
        best_dist: int = 999
        best_ratio: float = 1.0

        for pn in proper_nouns:
            # 長さ差が大きすぎたら skip
            if abs(len(pn) - len(query)) > max_distance:
                continue
            dist = _levenshtein_distance(query, pn)
            max_len = max(len(pn), len(query))
            ratio = dist / max_len if max_len > 0 else 1.0

            # 厳しい方が選ばれる
            if dist < best_dist or (dist == best_dist and ratio < best_ratio):
                best_term = pn
                best_dist = dist
                best_ratio = ratio

        if best_term and best_dist <= max_distance and best_ratio <= max_ratio:
            candidates.append({
                "id": cid,
                "matched_term": best_term,
                "distance": best_dist,
                "ratio": round(best_ratio, 3),
            })

    candidates.sort(key=lambda x: (x["distance"], x["ratio"]))
    return candidates[:top_k]


def fuzzy_match_against_titles(
    query: str,
    cases: list[dict[str, Any]],
    max_distance: int = DEFAULT_MAX_DISTANCE,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """クエリと各 case のタイトル全体（部分文字列マッチ）も含めて照合する.

    完全一致・部分文字列マッチ（クエリが title に含まれる）を最優先。
    続いて Levenshtein マッチ。

    Args:
        query: 検索クエリ。
        cases: load_cases() の結果。
        max_distance: Levenshtein 許容距離。
        top_k: 上位何件返すか。

    Returns:
        マッチした case のリスト。各要素:
            {
                "id": int,
                "title": str,
                "match_type": "substring"|"levenshtein",
                "distance": int,
                "ratio": float,
            }
    """
    if not query:
        return []

    substring_hits: list[dict[str, Any]] = []
    leven_hits: list[dict[str, Any]] = []

    for c in cases:
        title = c["title"]
        # 部分文字列マッチ最優先
        if query in title:
            substring_hits.append({
                "id": c["id"],
                "title": title,
                "match_type": "substring",
                "distance": 0,
                "ratio": 0.0,
            })
            continue

        # title に含まれるカタカナ/英大固有名詞と照合
        from extract_metadata import extract_proper_nouns
        proper_nouns = extract_proper_nouns(title)
        best_dist = 999
        best_ratio = 1.0
        for pn in proper_nouns:
            if abs(len(pn) - len(query)) > max_distance:
                continue
            dist = _levenshtein_distance(query, pn)
            max_len = max(len(pn), len(query))
            ratio = dist / max_len if max_len > 0 else 1.0
            if dist < best_dist:
                best_dist = dist
                best_ratio = ratio

        if best_dist <= max_distance and best_dist > 0:
            leven_hits.append({
                "id": c["id"],
                "title": title,
                "match_type": "levenshtein",
                "distance": best_dist,
                "ratio": round(best_ratio, 3),
            })

    substring_hits.sort(key=lambda x: x["id"])
    leven_hits.sort(key=lambda x: (x["distance"], x["ratio"]))
    return (substring_hits + leven_hits)[:top_k]


if __name__ == "__main__":
    # 単体動作テスト
    from load_data import load_cases, load_vocabulary

    cases = load_cases()
    vocab = load_vocabulary()
    title_pn = vocab["title_proper_nouns"]
    # JSON 経由ロード時は key が str になっているので int に戻す
    title_pn_intkey = {int(k): v for k, v in title_pn.items()}

    queries = [
        "ガーナーホテル",   # 完全一致想定
        "ガーナホテル",     # Layer 2 補正失敗時の想定
        "ガナホテル",       # より誤認識
        "コマツ",           # 完全一致
        "セネガルパビリオン",
        "セネガルバビリオン",  # 誤認識
        "KAIROS",
        "新宿",             # 漢字、proper_noun には抽出されない（カタカナ/英大のみ）
    ]

    for q in queries:
        print(f"\n=== query: 「{q}」 ===")
        hits_pn = fuzzy_match_cases(q, title_pn_intkey, top_k=3)
        print(f"  [proper_nouns マッチ] {len(hits_pn)} 件")
        for h in hits_pn:
            print(f"    id={h['id']:>3}  matched={h['matched_term']}  "
                  f"distance={h['distance']}  ratio={h['ratio']}")

        hits_title = fuzzy_match_against_titles(q, cases, top_k=3)
        print(f"  [title 部分文字列+proper_nouns マッチ] {len(hits_title)} 件")
        for h in hits_title:
            print(f"    id={h['id']:>3}  type={h['match_type']:>11}  "
                  f"distance={h['distance']}  title={h['title'][:40]}")
