"""Whisper による音声文字起こしモジュール.

OpenAI Whisper モデル（ローカル動作、small 既定）を用いて、
日本語音声を文字起こしする。初回ロード後はメモリキャッシュにより高速化。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

try:
    import whisper
except ImportError as e:
    raise ImportError(
        "openai-whisper が見つかりません。pip install openai-whisper を実行してください。"
    ) from e


_MODEL_CACHE: dict[str, Any] = {}


def load_whisper_model(model_name: str = "small") -> Any:
    """Whisper モデルをロードし、メモリにキャッシュする.

    初回呼び出し時はモデルファイルをダウンロード（small: 約500MB）。
    2回目以降の同名モデル呼び出しはキャッシュから即返却。

    Args:
        model_name: Whisper モデル名（"tiny", "base", "small", "medium", "large"）。

    Returns:
        ロード済みのWhisperモデルオブジェクト。

    Raises:
        RuntimeError: モデルのダウンロード／ロードに失敗。
    """
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]

    print(f"[transcribe] Whisperモデル '{model_name}' をロード中...")
    start = time.time()
    try:
        model = whisper.load_model(model_name)
    except Exception as e:
        raise RuntimeError(
            f"Whisperモデル '{model_name}' のロードに失敗しました。"
            f"初回はネットワーク接続が必要です（約500MBダウンロード）。"
        ) from e
    elapsed = time.time() - start
    print(f"[transcribe] ロード完了 ({elapsed:.2f}秒)")

    _MODEL_CACHE[model_name] = model
    return model


def transcribe_audio(wav_path: str, model: Any) -> dict[str, Any]:
    """指定WAVファイルを日本語として文字起こしする.

    Args:
        wav_path: 文字起こし対象のWAVファイルパス。
        model: load_whisper_model() で取得したモデル。

    Returns:
        以下のキーを持つ辞書:
            - text (str): 文字起こし結果
            - language (str): 検出言語（常に "ja"）
            - duration_sec (float): 処理時間

    Raises:
        FileNotFoundError: WAVファイルが存在しない。
        RuntimeError: 文字起こし処理に失敗。
    """
    p = Path(wav_path)
    if not p.exists():
        raise FileNotFoundError(f"音声ファイルが見つかりません: {wav_path}")

    start = time.time()
    try:
        result = model.transcribe(str(p), language="ja", verbose=False, fp16=False)
    except Exception as e:
        raise RuntimeError(f"文字起こし処理に失敗しました: {e}") from e
    elapsed = time.time() - start

    return {
        "text": result.get("text", "").strip(),
        "language": result.get("language", "ja"),
        "duration_sec": elapsed,
    }


if __name__ == "__main__":
    # 単体動作確認用
    import sys

    if len(sys.argv) < 2:
        print("使い方: python transcribe.py <wav_path> [model_name]")
        sys.exit(1)

    wav = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) >= 3 else "small"

    m = load_whisper_model(name)
    r = transcribe_audio(wav, m)
    print("\n結果:")
    print(f"  text:         {r['text']}")
    print(f"  language:     {r['language']}")
    print(f"  duration_sec: {r['duration_sec']:.2f}")
