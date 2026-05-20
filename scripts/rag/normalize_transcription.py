"""ASR 結果テキストの固有名詞補正（Layer 2: 後段ファジーマッチ）.

Whisper が誤認識したカタカナ固有名詞・英大文字固有名詞を、シーマ事例データから
抽出した既知の固有名詞リストと Levenshtein 距離で照合して補正する。

例:
    入力: 「パーナホテルの事例を見せて」
    候補抽出: ["パーナホテル"]
    最近傍探索: 「ガーナーホテル」(距離=2, ratio=0.29)
    補正後: 「ガーナーホテルの事例を見せて」

補正条件:
    - 候補は カタカナ3文字以上 または 英大文字+小文字混在3文字以上
    - Levenshtein 距離 / max(len(候補), len(語彙)) <= NORMALIZATION_RATIO_THRESHOLD
    - 距離 > 0（一致は素通し）
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import Levenshtein  # python-Levenshtein
except ImportError:
    Levenshtein = None  # type: ignore

# 候補抽出パターン（load_data.py と一致させる）
_KATAKANA_RE = re.compile(r"[ァ-ヴー]{3,}")
_UPPER_RE = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}\b")

# 補正判定の閾値
# 0.34 だと「テーマパター → テーマパーク」(distance=2, ratio=0.333) のような
# 境界ケースで誤補正することがあるため、0.30 に厳格化
NORMALIZATION_RATIO_THRESHOLD: float = 0.30  # distance / max(len_a, len_b)
MIN_CANDIDATE_LEN: int = 3


def _levenshtein_distance(a: str, b: str) -> int:
    """Pure-Python Levenshtein 距離（python-Levenshtein 未インストール時のフォールバック）."""
    if Levenshtein is not None:
        return Levenshtein.distance(a, b)
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                curr[j - 1] + 1,     # insertion
                prev[j] + 1,         # deletion
                prev[j - 1] + (ca != cb),  # substitution
            )
        prev = curr
    return prev[-1]


def find_best_match(
    candidate: str,
    vocabulary: list[str],
    ratio_threshold: float = NORMALIZATION_RATIO_THRESHOLD,
) -> tuple[str | None, int, float]:
    """候補文字列に最も近い語彙語を返す.

    Args:
        candidate: ASR 抽出された固有名詞候補。
        vocabulary: 既知の固有名詞リスト。
        ratio_threshold: distance / max(len) の許容上限。

    Returns:
        (最良マッチ語 or None, 距離, ratio) のタプル。
        マッチ無しの場合 (None, large_int, 1.0)。
    """
    if not candidate or len(candidate) < MIN_CANDIDATE_LEN:
        return None, 999, 1.0

    best_word: str | None = None
    best_dist: int = 999
    best_ratio: float = 1.0

    for word in vocabulary:
        # 長さ差が大きすぎる候補は早期 skip（パフォーマンス）
        if abs(len(word) - len(candidate)) > max(len(candidate), len(word)) * ratio_threshold:
            continue

        dist = _levenshtein_distance(candidate, word)
        max_len = max(len(candidate), len(word))
        ratio = dist / max_len if max_len > 0 else 1.0

        if ratio < best_ratio:
            best_word = word
            best_dist = dist
            best_ratio = ratio

    if best_word and best_ratio <= ratio_threshold:
        return best_word, best_dist, best_ratio
    return None, best_dist, best_ratio


def normalize(
    text: str,
    vocabulary: dict[str, Any] | list[str],
    ratio_threshold: float = NORMALIZATION_RATIO_THRESHOLD,
) -> tuple[str, list[dict[str, Any]]]:
    """ASR テキストの固有名詞を語彙ベースで補正する.

    Args:
        text: ASR 結果テキスト。
        vocabulary: build_vocabulary() の結果 dict、または proper_nouns の list[str]。
        ratio_threshold: 補正発動の閾値（distance/max_len）。

    Returns:
        (補正後テキスト, 補正履歴 list)
        補正履歴の各要素:
            {"original": str, "corrected": str, "distance": int, "ratio": float,
             "start": int, "end": int}
    """
    # vocabulary は dict（vocabulary.json）でも list でも受け取れるように
    if isinstance(vocabulary, dict):
        proper_nouns = vocabulary.get("proper_nouns", [])
    else:
        proper_nouns = list(vocabulary)

    if not proper_nouns:
        return text, []

    # 候補スパンを抽出（重複なし、開始位置順）
    spans: list[tuple[int, int, str]] = []
    seen_spans: set[tuple[int, int]] = set()
    for m in _KATAKANA_RE.finditer(text):
        key = (m.start(), m.end())
        if key not in seen_spans:
            spans.append((m.start(), m.end(), m.group()))
            seen_spans.add(key)
    for m in _UPPER_RE.finditer(text):
        key = (m.start(), m.end())
        if key not in seen_spans:
            spans.append((m.start(), m.end(), m.group()))
            seen_spans.add(key)

    spans.sort(key=lambda s: s[0])

    # 補正履歴を集めつつ、後方から置換（オフセット維持のため）
    corrections: list[dict[str, Any]] = []
    result = text
    for start, end, cand in reversed(spans):
        best, dist, ratio = find_best_match(cand, proper_nouns, ratio_threshold)
        if best is None or dist == 0 or best == cand:
            continue
        result = result[:start] + best + result[end:]
        corrections.append({
            "original": cand,
            "corrected": best,
            "distance": dist,
            "ratio": round(ratio, 3),
            "start": start,
            "end": end,
        })

    # corrections を start 順に並べ直して返す
    corrections.sort(key=lambda c: c["start"])
    return result, corrections


if __name__ == "__main__":
    # 単体動作テスト
    import sys

    from load_data import load_vocabulary

    vocab = load_vocabulary()
    print(f"[normalize] vocabulary: proper_nouns={len(vocab['proper_nouns'])} 語")
    print(f"[normalize] Levenshtein: {'C extension' if Levenshtein else 'pure-Python fallback'}")
    print()

    # 提供発話 / 想定誤認識のサンプル群
    test_cases = [
        ("ガーナーホテルの事例を見せて", "正常: 完全一致、補正なし"),
        ("ガーナホテルの事例を見せて", "誤認識: 「ー」欠落（1回目テストで発生）"),
        ("パーナホテルの事例を見せて", "誤認識: 「ガ→パ」「ー」欠落（cold時に発生）"),
        ("ガナホテルの事例を見せて", "誤認識: 「ー」2つ欠落"),
        ("セネガルバビリオン", "誤認識: 「パ→バ」"),
        ("カイロスを見せて", "誤認識: KAIROS のカタカナ表記"),
        ("コマツの事例", "正常"),
        ("プロジェクションマッピング", "正常: 完全一致"),
        ("プロジェクションマッビング", "誤認識: 「ピ→ビ」"),
        ("新宿駅のビジョン", "漢字+カタカナ"),
        ("レジャー&アウトドアジャパン", "正常"),
        ("ガーナホテル", "短いがマッチすべき"),
    ]

    # コマンドライン引数で個別テストも可能
    if len(sys.argv) > 1:
        test_cases = [(sys.argv[1], "ユーザー指定")]

    for original, note in test_cases:
        corrected, corrections = normalize(original, vocab)
        mark = "✓" if corrections else "—"
        print(f"{mark} 「{original}」 → 「{corrected}」  [{note}]")
        for c in corrections:
            print(f"    {c['original']} → {c['corrected']} "
                  f"(distance={c['distance']}, ratio={c['ratio']})")
