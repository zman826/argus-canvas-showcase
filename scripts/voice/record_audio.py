"""音声録音モジュール.

マイク入力をスペースキーのトグル操作で録音し、16kHz mono 16-bit PCM の
WAVファイルとして保存する。Argus Canvas Showcase の音声認識PoC用。

操作:
    1回目スペース押下: 録音開始
    2回目スペース押下: 録音停止
    max_seconds 経過: 自動停止
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
from scipy.io import wavfile

try:
    import keyboard
except ImportError as e:
    raise ImportError(
        "keyboard ライブラリが見つかりません。pip install keyboard を実行してください。"
    ) from e


SAMPLE_RATE: int = 16000
CHANNELS: int = 1
DTYPE: str = "int16"


def _list_input_devices() -> list[dict[str, Any]]:
    """利用可能な入力デバイスを列挙する.

    Returns:
        入力チャンネルを持つデバイス情報のリスト。
    """
    devices = sd.query_devices()
    return [d for d in devices if d.get("max_input_channels", 0) > 0]


def _wait_for_space_release() -> None:
    """スペースキーが離されるまで待機する（連続トリガー防止用デバウンス）."""
    while keyboard.is_pressed("space"):
        time.sleep(0.01)


def record_with_spacebar(output_path: str, max_seconds: int = 15) -> dict[str, Any]:
    """スペースキー操作でマイクから録音し、WAVファイルとして保存する.

    1回目スペース押下で録音開始、2回目押下で停止。max_seconds 経過で自動停止。

    Args:
        output_path: 保存先WAVファイルパス。
        max_seconds: 自動停止までの最大録音時間（秒）。デフォルト15秒。

    Returns:
        以下のキーを持つ辞書:
            - duration_sec (float): 実録音時間
            - sample_rate (int): サンプリングレート
            - path (str): 保存先パス

    Raises:
        RuntimeError: マイクデバイスが見つからない、または録音データが空。
        OSError: 書き込み権限がない、ディスク不足等。
    """
    if not _list_input_devices():
        raise RuntimeError(
            "マイクデバイスが見つかりません。Windows設定 > プライバシー > マイク "
            "でアクセス許可を確認してください。"
        )

    out_path = Path(output_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"出力ディレクトリの作成に失敗しました: {out_path.parent}") from e

    print("[record] スペースキーを押すと録音を開始します...")
    keyboard.wait("space")
    _wait_for_space_release()

    print(f"[record] 録音中... (スペースキーで停止、最大{max_seconds}秒)")

    frames: list[np.ndarray] = []

    def callback(indata: np.ndarray, frames_count: int, time_info: Any, status: Any) -> None:
        if status:
            sys.stderr.write(f"[record] 警告: {status}\n")
        frames.append(indata.copy())

    start_time = time.time()
    stopped_by_user = False

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=callback,
        ):
            while True:
                elapsed = time.time() - start_time
                if elapsed >= max_seconds:
                    print(f"[record] 最大録音時間 {max_seconds} 秒に達しました")
                    break
                if keyboard.is_pressed("space"):
                    stopped_by_user = True
                    _wait_for_space_release()
                    break
                time.sleep(0.05)
    except sd.PortAudioError as e:
        raise RuntimeError(f"録音中にPortAudioエラーが発生しました: {e}") from e

    duration = time.time() - start_time

    if not frames:
        raise RuntimeError("録音データが取得できませんでした（マイク無音の可能性）")

    audio = np.concatenate(frames, axis=0)
    if audio.ndim == 2 and audio.shape[1] == 1:
        audio = audio.flatten()

    try:
        wavfile.write(str(out_path), SAMPLE_RATE, audio)
    except OSError as e:
        raise OSError(f"WAVファイル書き込みに失敗しました: {out_path}") from e

    stop_reason = "ユーザー停止" if stopped_by_user else "タイムアウト"
    print(f"[record] 録音完了 ({duration:.2f}秒, {stop_reason}) -> {out_path}")

    return {
        "duration_sec": duration,
        "sample_rate": SAMPLE_RATE,
        "path": str(out_path),
    }


if __name__ == "__main__":
    # 単体動作確認用
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        result = record_with_spacebar(tmp_path)
        print("\n結果:", result)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
