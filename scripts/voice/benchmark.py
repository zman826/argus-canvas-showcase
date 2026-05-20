"""音声認識PoC ベンチマークスクリプト.

scripts/voice/samples/ 配下の全WAVファイルを処理し、
インテント正答率・処理時間を集計してCSV出力する。

ファイル命名規則:
    NNN_INTENT_description.wav
    例: 001_DIRECT_RECALL_ganerhotel.wav
        002_FILTER_SEARCH_hotel_led.wav
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Any

from classify_intent import classify_intent, load_system_prompt
from transcribe import load_whisper_model, transcribe_audio


_SCRIPT_DIR: Path = Path(__file__).resolve().parent
SAMPLES_DIR: Path = _SCRIPT_DIR / "samples"
RESULT_CSV: Path = _SCRIPT_DIR / "benchmark_result.csv"

_VALID_INTENTS: set[str] = {
    "DIRECT_RECALL",
    "FILTER_SEARCH",
    "SPEC_SEARCH",
    "CONSULTATION",
    "TERM_EXPLAIN",
    "COMPARISON",
    "NAVIGATION",
}

_FILENAME_PATTERN = re.compile(
    r"^\d+_(?P<intent>[A-Z_]+?)_.+\.wav$",
    re.IGNORECASE,
)

_CSV_FIELDS: list[str] = [
    "filename",
    "expected_intent",
    "transcription",
    "actual_intent",
    "confidence",
    "correct",
    "asr_time_sec",
    "llm_time_sec",
    "total_time_sec",
    "error",
]


def parse_expected_intent(filename: str) -> str | None:
    """ファイル名から期待インテントを抽出する.

    Args:
        filename: WAVファイル名（拡張子含む）。

    Returns:
        該当する7インテント名。マッチしない場合は None。
    """
    m = _FILENAME_PATTERN.match(filename)
    if not m:
        return None
    intent = m.group("intent").upper()
    return intent if intent in _VALID_INTENTS else None


def _process_one(wav: Path, model: Any, system_prompt: str) -> dict[str, Any]:
    """1ファイルを処理してCSV行データを返す."""
    expected = parse_expected_intent(wav.name)
    row: dict[str, Any] = {
        "filename": wav.name,
        "expected_intent": expected or "",
        "transcription": "",
        "actual_intent": "",
        "confidence": "",
        "correct": "",
        "asr_time_sec": "",
        "llm_time_sec": "",
        "total_time_sec": "",
        "error": "",
    }

    try:
        asr = transcribe_audio(str(wav), model)
        row["transcription"] = asr["text"]
        row["asr_time_sec"] = round(asr["duration_sec"], 2)
    except (FileNotFoundError, RuntimeError) as e:
        row["error"] = f"ASR失敗: {e}"
        return row

    try:
        cls = classify_intent(asr["text"], system_prompt)
    except Exception as e:  # noqa: BLE001
        row["error"] = f"分類例外: {e}"
        return row

    row["llm_time_sec"] = round(cls.get("duration_sec", 0.0), 2)
    row["total_time_sec"] = round(
        float(row["asr_time_sec"]) + float(row["llm_time_sec"]), 2
    )

    if "error" in cls:
        row["error"] = cls["error"]
        return row

    actual = cls.get("intent", "")
    row["actual_intent"] = actual
    row["confidence"] = cls.get("confidence", "")
    if expected:
        row["correct"] = "TRUE" if actual == expected else "FALSE"
    return row


def _print_summary(results: list[dict[str, Any]]) -> None:
    """集計サマリーを標準出力に表示する."""
    total = len(results)
    evaluable = [r for r in results if r["expected_intent"] and not r["error"]]
    correct = sum(1 for r in evaluable if r["correct"] == "TRUE")
    accuracy = (correct / len(evaluable) * 100) if evaluable else 0.0

    def _avg(key: str) -> float | None:
        vals = [
            float(r[key])
            for r in results
            if r[key] not in ("", None)
        ]
        return sum(vals) / len(vals) if vals else None

    avg_asr = _avg("asr_time_sec")
    avg_llm = _avg("llm_time_sec")
    avg_total = _avg("total_time_sec")

    print("\n" + "=" * 60)
    print("ベンチマーク集計")
    print("=" * 60)
    print(f"全件数: {total}")
    print(f"評価対象（命名規則あり&エラーなし）: {len(evaluable)}")
    print(f"正答数: {correct}")
    print(f"インテント正答率: {accuracy:.1f}%")
    if avg_asr is not None:
        print(f"平均ASR時間: {avg_asr:.2f}秒")
    if avg_llm is not None:
        print(f"平均LLM時間: {avg_llm:.2f}秒")
    if avg_total is not None:
        print(f"平均総時間: {avg_total:.2f}秒")
    print(f"\n結果保存先: {RESULT_CSV}")


def main() -> int:
    """エントリーポイント."""
    if not SAMPLES_DIR.exists():
        print(f"[benchmark] samples ディレクトリが存在しません: {SAMPLES_DIR}")
        return 1

    wavs = sorted(SAMPLES_DIR.glob("*.wav"))
    if not wavs:
        print(f"[benchmark] テスト音声(*.wav)が見つかりません: {SAMPLES_DIR}")
        print("[benchmark] 命名規則: NNN_INTENT_description.wav")
        print("[benchmark]   例: 001_DIRECT_RECALL_ganerhotel.wav")
        return 1

    print(f"[benchmark] {len(wavs)}件のテスト音声を処理します...")

    model = load_whisper_model("small")
    system_prompt = load_system_prompt()

    results: list[dict[str, Any]] = []
    for i, wav in enumerate(wavs, start=1):
        expected = parse_expected_intent(wav.name)
        print(f"\n[{i}/{len(wavs)}] {wav.name}  期待: {expected or '(命名規則なし)'}")
        row = _process_one(wav, model, system_prompt)
        results.append(row)

        if row["error"]:
            print(f"  → エラー: {row['error']}")
        else:
            print(f"  → 文字起こし: {row['transcription']}")
            print(
                f"  → 推定インテント: {row['actual_intent']}  "
                f"confidence={row['confidence']}  正誤={row['correct']}"
            )

    # CSVは Excel での文字化け防止のため utf-8-sig
    with RESULT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(results)

    _print_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
