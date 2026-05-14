# 音声認識PoC

Argus Canvas Showcase 用の音声→インテント分類PoC。
マイク録音 → Whisper（small）文字起こし → Gemma 4 E4B インテント分類を
完全ローカル動作で実行します。

## 構成

| ファイル | 役割 |
|---|---|
| `record_audio.py` | sounddevice + keyboard でスペースキー駆動録音 |
| `transcribe.py` | OpenAI Whisper（small, 日本語固定）で文字起こし |
| `classify_intent.py` | Ollama HTTP API 経由で gemma4:e4b に分類依頼 |
| `voice_to_intent.py` | 統合スクリプト（メイン）|
| `benchmark.py` | samples/*.wav 一括処理 → CSV出力 |
| `requirements_voice.txt` | Python依存パッケージ |
| `samples/` | テスト用WAV配置先（gitignore対象） |
| `logs/` | 実行結果JSONL保存先（gitignore対象） |

## 事前準備

### 1. 依存関係インストール

```powershell
pip install -r requirements_voice.txt
```

### 2. Whisper 初回ダウンロード（自動だが時間がかかる）

```powershell
python -c "import whisper; whisper.load_model('small')"
```

約500MBのモデルが `%USERPROFILE%\.cache\whisper\` にダウンロードされます。
初回のみネットワーク接続が必要です。

### 3. Ollama 起動と モデル取得

```powershell
ollama serve              # 別ターミナルで起動
ollama pull gemma4:e4b    # 初回のみ
ollama list               # gemma4:e4b が表示されることを確認
```

### 4. マイク権限

Windows 設定 > プライバシーとセキュリティ > マイク でアプリのアクセスを許可。

## 実行

作業ディレクトリ:
`E:\GoogleDrive_new\claude\argus-canvas-showcase\scripts\voice`

### 単発モード

```powershell
python voice_to_intent.py --once
```

スペースキーで録音開始 → スペースキー再押下で停止（または15秒で自動停止）。
結果JSONが標準出力と `logs/YYYYMMDD.jsonl` に保存されます。

### ループモード

```powershell
python voice_to_intent.py
```

毎回 Enter で続行、`q` + Enter で終了。

### ベンチマーク

```powershell
python benchmark.py
```

`samples/` 配下のWAVを一括処理。結果は `benchmark_result.csv` に出力。

#### サンプルファイル命名規則

```
NNN_INTENT_description.wav
```

例:
- `001_DIRECT_RECALL_ganerhotel.wav`
- `002_FILTER_SEARCH_hotel_led.wav`
- `003_TERM_EXPLAIN_cob.wav`

ファイル名のINTENT部分が期待インテントとなり、正答率算出に使われます。

## 出力JSONフォーマット

```json
{
  "timestamp": "2026-05-13T17:30:00",
  "raw_audio_duration_sec": 4.2,
  "transcription": "ガーナーホテルの事例を見せて",
  "transcription_language": "ja",
  "asr_time_sec": 0.8,
  "intent": "DIRECT_RECALL",
  "extracted_entities": {
    "client_name": "ガーナーホテル"
  },
  "confidence": 0.95,
  "llm_time_sec": 1.2,
  "total_time_sec": 2.0,
  "success": true,
  "error_message": null
}
```

## トラブルシューティング

| 症状 | 対応 |
|---|---|
| マイクが認識されない | `python -c "import sounddevice as sd; print(sd.query_devices())"` で確認。Windows設定のマイク権限も確認 |
| Whisperが遅い | GPU（CUDA）認識を確認。CPUのみなら `--whisper-model base` で速度↑（精度↓） |
| Ollama接続エラー | 別ターミナルで `ollama serve` を起動。`curl http://localhost:11434/api/tags` で疎通確認 |
| `gemma4:e4b` が無い | `ollama pull gemma4:e4b`。配信されていない地域では `gemma3:4b` 等を代替検討 |
| keyboard 権限エラー | 管理者として PowerShell を起動してから python を実行 |
| 文字化け（PowerShell） | `chcp 65001` でUTF-8コードページに切替、または `$env:PYTHONIOENCODING="utf-8"` |

## 制約

- 完全オフライン動作（Whisper初回ダウンロード時のみネット必要）
- Windows 11 想定（macOS/Linuxは sounddevice のドライバ次第）
- Python 3.11+
- `gemma4:e4b` は Ollama に事前 pull 済みであること

## 関連ドキュメント

- プロジェクト方針: `../../CLAUDE.md`
- 要件定義書 v0.3: `../../docs/requirements/v0.3_showcase_requirements.md`
- プロンプト設計: `../../docs/architecture/prompt_design.md`
- インテント分類プロンプト: `../../data/prompts/intent_classification_v1.md`
