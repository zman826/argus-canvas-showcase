"""Argus Canvas Showcase - tkinter ベース画像表示 UI (Phase C-1).

CLI 版 voice_to_intent.py の出力 JSON を画面に可視化する。
ショールーム向け簡易キオスク UI。

主要機能:
- スペースキー: 録音開始 / 停止 のトグル
- 録音後、自動で Whisper → 補正 → gemma3:4b 分類 → ChromaDB 検索を実行
- matched_cases[0] の mainPhoto を画面中央に大きく表示
- 左右矢印キー: matched_cases 内を前後移動（top-5 を切替）
- F11: フルスクリーン切替（ショールーム展示時）
- Esc: 終了

スレッドモデル:
- メインスレッド: tkinter mainloop
- ワーカースレッド: ASR + 分類 + RAG
- 通信: queue.Queue + tkinter after() でポーリング
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import font as tkfont
from typing import Any

import numpy as np
import sounddevice as sd
from PIL import Image, ImageTk
from scipy.io import wavfile

# scripts/rag/ を import path に追加
_SCRIPT_DIR: Path = Path(__file__).resolve().parent
_RAG_DIR: Path = _SCRIPT_DIR.parent / "rag"
if _RAG_DIR.exists() and str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

from build_index import get_collection, get_embedding_model  # noqa: E402
from classify_intent import classify_intent, load_system_prompt  # noqa: E402
from load_data import (  # noqa: E402
    build_image_manifest,
    find_cima_data_dir,
    load_cases,
    load_vocabulary,
)
from normalize_transcription import normalize  # noqa: E402
from search_cases import search as rag_search  # noqa: E402
from transcribe import load_whisper_model, transcribe_audio  # noqa: E402

# 録音設定
SAMPLE_RATE: int = 16000
CHANNELS: int = 1
DTYPE: str = "int16"
MAX_RECORD_SEC: int = 15

# UI スタイル
BG_COLOR: str = "#0a0a0a"
TEXT_COLOR: str = "#f0f0f0"
ACCENT_COLOR: str = "#4a9eff"
STATUS_COLOR_IDLE: str = "#888888"
STATUS_COLOR_REC: str = "#ff4040"
STATUS_COLOR_PROC: str = "#ffaa40"
STATUS_COLOR_DONE: str = "#40ff80"


class Recorder:
    """sd.InputStream を使ったトグル式レコーダ（keyboard モジュール非依存）."""

    def __init__(self) -> None:
        self.stream: sd.InputStream | None = None
        self.frames: list[np.ndarray] = []
        self.start_time: float = 0.0

    def start(self) -> None:
        """録音開始."""
        self.frames = []
        self.start_time = time.time()

        def callback(indata: np.ndarray, frame_count: int,
                     time_info: Any, status: Any) -> None:
            if status:
                sys.stderr.write(f"[recorder] {status}\n")
            self.frames.append(indata.copy())

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=callback,
        )
        self.stream.start()

    def stop_and_save(self, wav_path: Path) -> float:
        """録音停止して WAV 保存、録音時間（秒）を返す."""
        if self.stream is None:
            return 0.0
        self.stream.stop()
        self.stream.close()
        self.stream = None
        duration = time.time() - self.start_time
        if not self.frames:
            raise RuntimeError("録音データが空（マイク無音の可能性）")
        audio = np.concatenate(self.frames, axis=0)
        if audio.ndim == 2 and audio.shape[1] == 1:
            audio = audio.flatten()
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wavfile.write(str(wav_path), SAMPLE_RATE, audio)
        return duration

    def is_recording(self) -> bool:
        return self.stream is not None


class ShowcaseUI:
    """Argus Canvas Showcase メインUI."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Argus Canvas Showcase")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("1280x800")

        # 初期化フラグ
        self.recorder = Recorder()
        self.queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.preload_done = False
        self.is_fullscreen = False

        # 表示用データ
        self.cases_by_id: dict[int, dict[str, Any]] = {}
        self.image_manifest: dict[str, Any] = {}
        self.current_hits: list[dict[str, Any]] = []
        self.current_index: int = 0
        self._image_ref: ImageTk.PhotoImage | None = None
        self._thumbnail_refs: list[ImageTk.PhotoImage] = []

        # 各種モデル（ワーカースレッドで使う、メインスレッドは触らない）
        self.whisper_model: Any = None
        self.system_prompt: str = ""
        self.vocabulary: dict[str, Any] = {}
        self.temp_dir = _SCRIPT_DIR / "_temp"

        self._build_ui()
        self._bind_keys()

        # バックグラウンドでモデル群を pre-load
        threading.Thread(target=self._preload_worker, daemon=True).start()

        # キューポーリング開始
        self.root.after(100, self._poll_queue)

    # ─── UI 構築 ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        title_font = tkfont.Font(family="Yu Gothic UI", size=28, weight="bold")
        subtitle_font = tkfont.Font(family="Yu Gothic UI", size=14)
        status_font = tkfont.Font(family="Yu Gothic UI", size=11)
        hint_font = tkfont.Font(family="Yu Gothic UI", size=9)

        # ステータスバー（最上部）
        self.status_var = tk.StringVar(value="モデルをロード中...")
        self.status_label = tk.Label(
            self.root, textvariable=self.status_var,
            font=status_font, fg=STATUS_COLOR_PROC, bg=BG_COLOR,
            anchor="w", padx=20, pady=8,
        )
        self.status_label.pack(side=tk.TOP, fill=tk.X)

        # タイトル
        self.title_var = tk.StringVar(value="Argus Canvas Showcase")
        self.title_label = tk.Label(
            self.root, textvariable=self.title_var,
            font=title_font, fg=TEXT_COLOR, bg=BG_COLOR,
            wraplength=1200, justify="center",
        )
        self.title_label.pack(side=tk.TOP, pady=(10, 5))

        # メイン画像
        self.image_label = tk.Label(self.root, bg=BG_COLOR)
        self.image_label.pack(side=tk.TOP, pady=10, expand=True)

        # サブタイトル
        self.subtitle_var = tk.StringVar(
            value="スペースキーを押して発話してください")
        self.subtitle_label = tk.Label(
            self.root, textvariable=self.subtitle_var,
            font=subtitle_font, fg="#cccccc", bg=BG_COLOR,
            wraplength=1200, justify="center",
        )
        self.subtitle_label.pack(side=tk.TOP, pady=5)

        # タグチップ
        self.tags_var = tk.StringVar(value="")
        self.tags_label = tk.Label(
            self.root, textvariable=self.tags_var,
            font=subtitle_font, fg=ACCENT_COLOR, bg=BG_COLOR,
        )
        self.tags_label.pack(side=tk.TOP, pady=5)

        # サムネイル帯（top-5 の matched_cases）
        self.thumb_frame = tk.Frame(self.root, bg=BG_COLOR, height=120)
        self.thumb_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # フッターヒント
        hint_text = (
            "[Space] 録音開始/停止    "
            "[← →] 結果切替    "
            "[F11] フルスクリーン    "
            "[Esc] 終了"
        )
        self.hint_label = tk.Label(
            self.root, text=hint_text,
            font=hint_font, fg="#666666", bg=BG_COLOR,
        )
        self.hint_label.pack(side=tk.BOTTOM, pady=4)

    def _bind_keys(self) -> None:
        self.root.bind("<space>", lambda e: self._on_space())
        self.root.bind("<Right>", lambda e: self._navigate(+1))
        self.root.bind("<Left>", lambda e: self._navigate(-1))
        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self._on_escape())

    def _toggle_fullscreen(self) -> None:
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)

    def _on_escape(self) -> None:
        if self.is_fullscreen:
            self.is_fullscreen = False
            self.root.attributes("-fullscreen", False)
        else:
            self.root.quit()

    # ─── プリロード ────────────────────────────────────────────

    def _preload_worker(self) -> None:
        """重いモデル群をワーカースレッドでロード."""
        try:
            self.queue.put(("status", ("Whisper small ロード中...", STATUS_COLOR_PROC)))
            self.whisper_model = load_whisper_model("small")

            self.queue.put(("status", ("事例データ + 画像マニフェストロード中...", STATUS_COLOR_PROC)))
            data_dir = find_cima_data_dir()
            cases = load_cases(data_dir)
            self.cases_by_id = {c["id"]: c for c in cases}
            manifest = build_image_manifest(cases, data_dir)
            self.image_manifest = manifest["by_id"]

            self.queue.put(("status", ("語彙データロード中...", STATUS_COLOR_PROC)))
            self.vocabulary = load_vocabulary(data_dir)

            self.queue.put(("status", ("ChromaDB 接続中...", STATUS_COLOR_PROC)))
            _ = get_collection()  # 存在確認

            self.queue.put(("status", ("システムプロンプトロード中...", STATUS_COLOR_PROC)))
            self.system_prompt = load_system_prompt()

            self.preload_done = True
            self.queue.put(("status", ("準備完了 - スペースキーで発話開始", STATUS_COLOR_IDLE)))
        except Exception as e:  # noqa: BLE001
            self.queue.put(("status", (f"初期化エラー: {e}", "#ff4040")))

    # ─── スペースキー処理 ─────────────────────────────────────

    def _on_space(self) -> None:
        if not self.preload_done:
            self.queue.put(("status", ("まだ準備中です...", STATUS_COLOR_PROC)))
            return

        if not self.recorder.is_recording():
            # 録音開始
            try:
                self.recorder.start()
                self.queue.put(("status", ("録音中... (もう一度スペースで停止)", STATUS_COLOR_REC)))
            except Exception as e:  # noqa: BLE001
                self.queue.put(("status", (f"録音開始失敗: {e}", "#ff4040")))
        else:
            # 録音停止 → 処理開始
            wav_path = self.temp_dir / f"recording_{int(time.time() * 1000)}.wav"
            try:
                duration = self.recorder.stop_and_save(wav_path)
                self.queue.put(("status",
                                (f"録音完了 ({duration:.1f}秒) - 認識中...",
                                 STATUS_COLOR_PROC)))
                threading.Thread(
                    target=self._process_worker,
                    args=(wav_path,),
                    daemon=True,
                ).start()
            except Exception as e:  # noqa: BLE001
                self.queue.put(("status", (f"録音保存失敗: {e}", "#ff4040")))

    # ─── パイプライン実行（ワーカースレッド）─────────────────

    def _process_worker(self, wav_path: Path) -> None:
        try:
            t0 = time.time()

            # Layer 1: Whisper with initial_prompt
            asr = transcribe_audio(
                str(wav_path), self.whisper_model,
                initial_prompt=self.vocabulary.get("whisper_initial_prompt"),
            )
            self.queue.put(("status",
                            (f"認識: 「{asr['text']}」 - 補正中...", STATUS_COLOR_PROC)))

            # Layer 2: normalize
            corrected, _ = normalize(asr["text"], self.vocabulary)

            # gemma3:4b 分類
            self.queue.put(("status", ("インテント分類中...", STATUS_COLOR_PROC)))
            cls = classify_intent(corrected, self.system_prompt)
            if "error" in cls:
                self.queue.put(("status",
                                (f"分類エラー: {cls['error'][:80]}", "#ff4040")))
                return

            intent = cls.get("intent")
            entities = cls.get("extracted_entities", {}) or {}

            # NAVIGATION 処理（RAG をスキップして UI 操作）
            if intent == "NAVIGATION":
                action = entities.get("action", "")
                if action in ("next", "次"):
                    self.queue.put(("navigate", +1))
                elif action in ("back", "戻る", "previous"):
                    self.queue.put(("navigate", -1))
                else:
                    self.queue.put(("status",
                                    (f"NAVIGATION ({action}) - 未対応", STATUS_COLOR_IDLE)))
                return

            # RAG 検索
            self.queue.put(("status", ("検索中...", STATUS_COLOR_PROC)))
            rag_result = rag_search(
                intent=intent, entities=entities, query=corrected, top_k=5,
            )
            hits = rag_result.get("matched_cases", [])

            elapsed = time.time() - t0
            status_msg = (
                f"完了 ({elapsed:.1f}秒)  intent={intent}  hits={len(hits)}"
                f"  «{corrected}»"
            )
            self.queue.put(("status", (status_msg, STATUS_COLOR_DONE)))
            self.queue.put(("hits", hits))

            # ログを残す
            self._append_log({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "transcription_raw": asr["text"],
                "transcription": corrected,
                "intent": intent,
                "entities": entities,
                "hits": [{"id": h["id"], "title": h["title"]} for h in hits],
                "elapsed_sec": round(elapsed, 2),
            })
        except Exception as e:  # noqa: BLE001
            self.queue.put(("status", (f"処理失敗: {e}", "#ff4040")))
        finally:
            wav_path.unlink(missing_ok=True)

    def _append_log(self, entry: dict[str, Any]) -> None:
        log_dir = _SCRIPT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{datetime.now().strftime('%Y%m%d')}-ui.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ─── キューポーリング ─────────────────────────────────────

    def _poll_queue(self) -> None:
        try:
            while True:
                event_type, data = self.queue.get_nowait()
                if event_type == "status":
                    msg, color = data
                    self.status_var.set(msg)
                    self.status_label.config(fg=color)
                elif event_type == "hits":
                    self._set_hits(data)
                elif event_type == "navigate":
                    self._navigate(data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ─── 結果表示 ─────────────────────────────────────────────

    def _set_hits(self, hits: list[dict[str, Any]]) -> None:
        self.current_hits = hits
        self.current_index = 0
        if not hits:
            self.title_var.set("該当なし")
            self.subtitle_var.set("該当する事例が見つかりませんでした")
            self.tags_var.set("")
            self.image_label.config(image="")
            self._image_ref = None
            self._update_thumbnails()
            return
        self._display_current()
        self._update_thumbnails()

    def _navigate(self, delta: int) -> None:
        if not self.current_hits:
            return
        self.current_index = (self.current_index + delta) % len(self.current_hits)
        self._display_current()
        self._update_thumbnails()

    def _display_current(self) -> None:
        hit = self.current_hits[self.current_index]
        case_id = hit["id"]
        case = self.cases_by_id.get(case_id, {})
        title = case.get("title", hit.get("title", f"ID {case_id}"))
        subtitle = case.get("subTitle", "")
        tags = case.get("tag", [])

        # 「3 / 5」みたいなインジケータを title に付加
        n = len(self.current_hits)
        indicator = f" ({self.current_index + 1}/{n})" if n > 1 else ""
        self.title_var.set(title + indicator)
        self.subtitle_var.set(subtitle)
        self.tags_var.set("  ".join(f"# {t}" for t in tags) if tags else "")

        # メイン画像
        img_info = self.image_manifest.get(str(case_id)) or self.image_manifest.get(case_id)
        if img_info and img_info.get("main"):
            self._load_image_into(self.image_label, Path(img_info["main"]),
                                  max_size=(900, 500))
        else:
            self.image_label.config(image="", text="(画像なし)", fg="#666666")
            self._image_ref = None

    def _load_image_into(self, label: tk.Label, path: Path,
                         max_size: tuple[int, int]) -> None:
        try:
            img = Image.open(path)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            label.config(image=photo, text="")
            self._image_ref = photo  # GC 防止：参照を保持
        except Exception as e:  # noqa: BLE001
            label.config(image="", text=f"(画像読み込み失敗: {e})", fg="#ff8080")
            self._image_ref = None

    def _update_thumbnails(self) -> None:
        # 既存サムネイルクリア
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self._thumbnail_refs = []

        if not self.current_hits:
            return

        for i, hit in enumerate(self.current_hits[:5]):
            case_id = hit["id"]
            img_info = (
                self.image_manifest.get(str(case_id))
                or self.image_manifest.get(case_id)
            )
            border = ACCENT_COLOR if i == self.current_index else BG_COLOR
            cell = tk.Frame(self.thumb_frame, bg=border, padx=2, pady=2)
            cell.pack(side=tk.LEFT, padx=4)
            thumb_label = tk.Label(cell, bg="#222222", width=120, height=80)
            thumb_label.pack()
            if img_info and img_info.get("main"):
                try:
                    img = Image.open(img_info["main"])
                    img.thumbnail((120, 80), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    thumb_label.config(image=photo, width=img.width, height=img.height)
                    self._thumbnail_refs.append(photo)
                except Exception:  # noqa: BLE001
                    thumb_label.config(text=f"id={case_id}", fg="#999999")
            id_label = tk.Label(cell, text=f"#{case_id}", fg="#aaaaaa",
                                bg=border, font=("Yu Gothic UI", 8))
            id_label.pack()

    # ─── 起動 ──────────────────────────────────────────────────

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    ui = ShowcaseUI()
    ui.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
