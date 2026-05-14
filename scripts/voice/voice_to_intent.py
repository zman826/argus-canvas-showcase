"""音声→インテント分類 統合スクリプト.

マイク録音 → Whisper文字起こし → Gemma 4インテント分類 を統合し、
仕様書に定めるJSON形式で標準出力およびログファイルに出力する。

実行例:
    python voice_to_intent.py             # ループモード（q + Enter で終了）
    python voice_to_intent.py --once      # 単発モード
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from classify_intent import classify_intent, load_system_prompt
from record_audio import record_with_spacebar
from transcribe import load_whisper_model, transcribe_audio


_SCRIPT_DIR: Path = Path(__file__).resolve().parent
LOG_DIR: Path = _SCRIPT_DIR / "logs"
TEMP_DIR: Path = _SCRIPT_DIR / "_temp"


def _empty_result() -> dict[str, Any]:
    """仕様書記載の出力JSONスキーマに準拠した空のテンプレートを返す."""
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "raw_audio_duration_sec": None,
        "transcription": None,
        "transcription_language": None,
        "asr_time_sec": None,
        "intent": None,
        "extracted_entities": {},
        "confidence": None,
        "llm_time_sec": None,
        "total_time_sec": None,
        "success": False,
        "error_message": None,
    }


def run_once(model: Any, system_prompt: str) -> dict[str, Any]:
    """1回分の録音→ASR→分類サイクルを実行する.

    Args:
        model: Whisper モデル（load_whisper_model() の戻り値）。
        system_prompt: 分類用システムプロンプト。

    Returns:
        仕様書定義の出力JSONスキーマに沿った辞書。
    """
    result = _empty_result()

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = TEMP_DIR / f"recording_{int(time.time() * 1000)}.wav"

    try:
        rec = record_with_spacebar(str(wav_path))
        result["raw_audio_duration_sec"] = round(rec["duration_sec"], 2)
    except (RuntimeError, OSError) as e:
        result["error_message"] = f"録音失敗: {e}"
        return result

    # 発話終了からの処理時間計測開始
    processing_start = time.time()

    try:
        print("[main] 文字起こし中...")
        asr = transcribe_audio(str(wav_path), model)
        result["transcription"] = asr["text"]
        result["transcription_language"] = asr["language"]
        result["asr_time_sec"] = round(asr["duration_sec"], 2)
        print(f"[main]   → 「{asr['text']}」")
    except (FileNotFoundError, RuntimeError) as e:
        result["error_message"] = f"文字起こし失敗: {e}"
        result["total_time_sec"] = round(time.time() - processing_start, 2)
        _safe_delete(wav_path)
        return result

    try:
        print("[main] インテント分類中...")
        cls = classify_intent(asr["text"], system_prompt)
    except Exception as e:  # noqa: BLE001 - 想定外のクライアント例外も拾う
        result["error_message"] = f"分類処理例外: {e}"
        result["total_time_sec"] = round(time.time() - processing_start, 2)
        _safe_delete(wav_path)
        return result

    result["llm_time_sec"] = round(cls.get("duration_sec", 0.0), 2)

    if "error" in cls:
        result["error_message"] = cls["error"]
    else:
        result["intent"] = cls.get("intent")
        result["extracted_entities"] = cls.get("extracted_entities", {}) or {}
        result["confidence"] = cls.get("confidence")
        result["success"] = True

    result["total_time_sec"] = round(time.time() - processing_start, 2)

    _safe_delete(wav_path)
    return result


def _safe_delete(path: Path) -> None:
    """一時WAVファイルを安全に削除する（プライバシー保護のため録音は非保持）."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def append_log(result: dict[str, Any]) -> None:
    """結果を日付別 JSONL ファイルに追記する.

    Args:
        result: run_once() の戻り値。
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{datetime.now().strftime('%Y%m%d')}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def _print_result(result: dict[str, Any]) -> None:
    """結果JSONを整形して標準出力に表示する."""
    print("\n" + "=" * 60)
    print("結果")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 60)


def main() -> int:
    """エントリーポイント."""
    parser = argparse.ArgumentParser(
        description="音声→インテント分類PoC (Argus Canvas Showcase)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="単発モード（録音→処理→終了）",
    )
    parser.add_argument(
        "--whisper-model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisperモデル名（既定: small）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Argus Canvas Showcase - 音声認識PoC")
    print("=" * 60)

    try:
        model = load_whisper_model(args.whisper_model)
    except RuntimeError as e:
        print(f"[main] 致命的エラー: {e}", file=sys.stderr)
        return 1

    system_prompt = load_system_prompt()

    if args.once:
        result = run_once(model, system_prompt)
        _print_result(result)
        append_log(result)
        return 0 if result["success"] else 2

    print("[main] ループモード開始（'q' + Enter で終了、Ctrl+C で中断）")
    while True:
        try:
            result = run_once(model, system_prompt)
            _print_result(result)
            append_log(result)

            print("\n続行: Enter / 終了: q")
            user_input = input().strip().lower()
            if user_input == "q":
                print("[main] 終了します")
                break
        except KeyboardInterrupt:
            print("\n[main] Ctrl+C で中断しました")
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
