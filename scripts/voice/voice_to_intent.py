"""音声→インテント分類 統合スクリプト.

マイク録音 → Whisper文字起こし（Layer 1: 語彙バイアス）→
固有名詞補正（Layer 2: 後段ファジー）→ Gemma 4インテント分類 を統合し、
仕様書に定めるJSON形式で標準出力およびログファイルに出力する。

実行例:
    python voice_to_intent.py             # ループモード（q + Enter で終了）
    python voice_to_intent.py --once      # 単発モード
    python voice_to_intent.py --no-bias   # Layer 1/2 を無効化して比較
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

# scripts/rag/ を import path に追加（Layer 1/2 のために load_vocabulary + normalize を使う）
_RAG_DIR: Path = _SCRIPT_DIR.parent / "rag"
if _RAG_DIR.exists() and str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

try:
    from load_data import load_vocabulary
    from normalize_transcription import normalize
    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False

# RAG 検索（オプション、scripts/rag/ + chromadb 構築済みのときのみ有効）
try:
    from search_cases import search as rag_search
    from build_index import get_collection, get_embedding_model
    _SEARCH_AVAILABLE = True
except ImportError:
    _SEARCH_AVAILABLE = False


def _empty_result() -> dict[str, Any]:
    """仕様書記載の出力JSONスキーマに準拠した空のテンプレートを返す."""
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "raw_audio_duration_sec": None,
        "transcription_raw": None,       # Layer 1 適用後（Whisper 生出力）
        "transcription": None,           # Layer 2 適用後（normalize 補正済み）
        "transcription_corrections": [],  # Layer 2 で施した補正の履歴
        "transcription_language": None,
        "asr_time_sec": None,
        "normalize_time_sec": None,
        "intent": None,
        "extracted_entities": {},
        "confidence": None,
        "llm_time_sec": None,
        "matched_cases": [],              # RAG 検索結果（上位 5 件）
        "rag_time_sec": None,             # RAG 検索の所要時間
        "total_time_sec": None,
        "success": False,
        "error_message": None,
    }


def run_once(
    model: Any,
    system_prompt: str,
    vocabulary: dict[str, Any] | None = None,
    use_bias: bool = True,
    use_rag: bool = True,
) -> dict[str, Any]:
    """1回分の録音→ASR→正規化→分類→RAG検索 サイクルを実行する.

    Args:
        model: Whisper モデル（load_whisper_model() の戻り値）。
        system_prompt: 分類用システムプロンプト。
        vocabulary: load_vocabulary() の結果。None なら Layer 1/2 をスキップ。
        use_bias: False で Layer 1/2 を強制無効化（比較検証用）。
        use_rag: False で RAG 検索ステップをスキップ。

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

    # Layer 1: Whisper initial_prompt
    initial_prompt = None
    if use_bias and vocabulary:
        initial_prompt = vocabulary.get("whisper_initial_prompt")

    try:
        print("[main] 文字起こし中...")
        asr = transcribe_audio(str(wav_path), model, initial_prompt=initial_prompt)
        raw_text = asr["text"]
        result["transcription_raw"] = raw_text
        result["transcription_language"] = asr["language"]
        result["asr_time_sec"] = round(asr["duration_sec"], 2)
        print(f"[main]   → 「{raw_text}」")
    except (FileNotFoundError, RuntimeError) as e:
        result["error_message"] = f"文字起こし失敗: {e}"
        result["total_time_sec"] = round(time.time() - processing_start, 2)
        _safe_delete(wav_path)
        return result

    # Layer 2: 後段固有名詞補正
    text_for_intent = raw_text
    if use_bias and vocabulary:
        norm_start = time.time()
        corrected, corrections = normalize(raw_text, vocabulary)
        result["normalize_time_sec"] = round(time.time() - norm_start, 3)
        result["transcription_corrections"] = corrections
        text_for_intent = corrected
        if corrections:
            print(f"[main] 補正: {len(corrections)} 件")
            for c in corrections:
                print(f"  「{c['original']}」 → 「{c['corrected']}」 "
                      f"(dist={c['distance']}, ratio={c['ratio']})")
            print(f"[main]   ↳ 「{corrected}」")
    result["transcription"] = text_for_intent

    try:
        print("[main] インテント分類中...")
        cls = classify_intent(text_for_intent, system_prompt)
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

    # RAG 検索ステップ（intent 分類成功時のみ）
    if use_rag and _SEARCH_AVAILABLE and result["success"] and result["intent"] != "NAVIGATION":
        try:
            print(f"[main] RAG 検索中（intent={result['intent']}）...")
            rag_result = rag_search(
                intent=result["intent"],
                entities=result["extracted_entities"],
                query=text_for_intent,
                top_k=5,
            )
            result["matched_cases"] = rag_result.get("matched_cases", [])
            result["rag_time_sec"] = rag_result.get("rag_time_sec")
            if "error" in rag_result:
                print(f"[main]   RAG 検索エラー: {rag_result['error']}", file=sys.stderr)
            else:
                hit_summary = [
                    f"id={h['id']}({h['match_type']})"
                    for h in result["matched_cases"][:3]
                ]
                print(f"[main]   ヒット {len(result['matched_cases'])} 件: "
                      f"{', '.join(hit_summary)}")
        except Exception as e:  # noqa: BLE001
            print(f"[main]   RAG 検索失敗: {e}", file=sys.stderr)
            result["matched_cases"] = []

    result["total_time_sec"] = round(time.time() - processing_start, 2)

    _safe_delete(wav_path)
    return result


def _safe_delete(path: Path) -> None:
    """一時WAVファイルを安全に削除する（プライバシー保護のため録音は非保持）."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def warmup_ollama(system_prompt: str) -> None:
    """Ollama にダミー推論を送り、gemma3:4b を VRAM に事前ロードする.

    起動時に5〜30秒の cold start を吸収しておくことで、来場者の初回発話に対する
    レイテンシが warm cycle 並みに短縮される。Ollama の keep_alive（既定 5分）が
    切れると再 cold になるため、長時間アイドル後の運用では再 warmup が必要。

    Args:
        system_prompt: classify_intent と同じシステムプロンプト。
    """
    print("[main] Ollama (gemma3:4b) warmup 中... (cold時は15〜30秒)")
    start = time.time()
    result = classify_intent("テスト", system_prompt)
    elapsed = time.time() - start
    if "error" in result:
        print(
            f"[main] warmup 警告: {result['error']} ({elapsed:.1f}秒)",
            file=sys.stderr,
        )
    else:
        print(f"[main] warmup 完了 ({elapsed:.1f}秒、次回以降は warm)")


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
    parser.add_argument(
        "--no-bias",
        action="store_true",
        help="ASR 語彙バイアス（Layer 1/2）を無効化（比較検証用）",
    )
    parser.add_argument(
        "--no-rag",
        action="store_true",
        help="RAG 検索ステップをスキップ（インテント分類までで止める）",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="起動時の Ollama warmup をスキップ（テスト/開発用）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Argus Canvas Showcase - 音声認識PoC")
    print("=" * 60)

    # 語彙ロード（Layer 1/2 用）
    vocabulary: dict[str, Any] | None = None
    use_bias = not args.no_bias
    if use_bias and _RAG_AVAILABLE:
        try:
            vocabulary = load_vocabulary()
            pn_count = len(vocabulary.get("proper_nouns", []))
            ip_len = len(vocabulary.get("whisper_initial_prompt", ""))
            print(f"[main] ASR語彙バイアス有効: proper_nouns={pn_count}語, "
                  f"initial_prompt={ip_len}字")
        except (FileNotFoundError, ValueError) as e:
            print(f"[main] 警告: 語彙ロード失敗、Layer 1/2 をスキップ: {e}",
                  file=sys.stderr)
            vocabulary = None
    elif use_bias and not _RAG_AVAILABLE:
        print("[main] 警告: scripts/rag が見つからず、Layer 1/2 をスキップ",
              file=sys.stderr)
    else:
        print("[main] ASR語彙バイアス無効化（--no-bias）")

    try:
        model = load_whisper_model(args.whisper_model)
    except RuntimeError as e:
        print(f"[main] 致命的エラー: {e}", file=sys.stderr)
        return 1

    # RAG: ChromaDB の存在だけ確認、e5-small モデルは遅延ロード（RAM 節約）
    # 同時ロードすると Whisper(500MB) + e5-small(470MB) で Ollama の RAM が枯渇するため、
    # 初回 RAG クエリ時に e5-small をロード（その1回だけ 7-8秒、以降 warm）
    use_rag = not args.no_rag
    if use_rag and _SEARCH_AVAILABLE:
        try:
            collection = get_collection()
            n_docs = collection.count()
            print(f"[main] RAG 有効: ChromaDB {n_docs} 件（e5-smallは初回検索時に遅延ロード）")
        except Exception as e:  # noqa: BLE001
            print(f"[main] 警告: ChromaDB アクセス失敗、検索ステップ無効化: {e}",
                  file=sys.stderr)
            use_rag = False
    elif use_rag and not _SEARCH_AVAILABLE:
        print("[main] 警告: search_cases/build_index が見つからず、RAG 無効",
              file=sys.stderr)
        use_rag = False
    else:
        print("[main] RAG 検索無効化（--no-rag）")

    system_prompt = load_system_prompt()

    # Ollama warmup（cold start 対策、来場者の初回発話レイテンシを短縮）
    if not args.no_warmup:
        warmup_ollama(system_prompt)
    else:
        print("[main] Ollama warmup スキップ（--no-warmup）")

    if args.once:
        result = run_once(model, system_prompt, vocabulary, use_bias, use_rag)
        _print_result(result)
        append_log(result)
        return 0 if result["success"] else 2

    print("[main] ループモード開始（'q' + Enter で終了、Ctrl+C で中断）")
    while True:
        try:
            result = run_once(model, system_prompt, vocabulary, use_bias, use_rag)
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
