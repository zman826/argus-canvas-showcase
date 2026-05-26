# Argus Canvas Showcase 開発ガイド

## プロジェクト概要

シーマ社の事例検索サイネージ「Argus Canvas Showcase」。
ローカルLLMで音声駆動し、シーマの導入事例ページを即時表示するWindowsアプリです。

**目的**：シーマショールーム来訪客に対し、音声入力で関連事例を即座に呼び出し、
大型ディスプレイで提示する営業デモツール。完全オフライン動作（買い切り型・USB更新運用）。

**リポジトリ**：https://github.com/zman826/argus-canvas-showcase

## 関連会社・ブランド

- **シーマ**：映像機器・LEDディスプレイ・音響機器のシステム設計・施工・レンタル会社。
  本プロジェクトのメイン顧客であり、アーガス企画のグループ会社。
  ※グループ会社のため敬称は付けない（社内ルール）
- **アーガス企画**：デジタルサイネージ・インタラクティブコンテンツ開発会社。
  本プロジェクトの開発主体。
- **OSMIL**：アーガス企画が独自開発した映像表示制御エンジン。
  ※必ず大文字表記
- **「キャンバスになろうよ。」**：アーガス企画のコアブランドメッセージ。

## 技術スタック

| 層 | 技術 |
|---|---|
| UI層（PoC） | CLI (`showcase_ui.py`)、本番化フェーズで WPF/.NET 8 |
| ASR | Whisper small（ローカル、CPU/GPU 自動判定） |
| 固有名詞補正 | ASR 3層防御（後述） |
| AI推論 | Ollama + gemma3:4b（PoC環境）／gemma4:e4b（本番、VRAM 16GB+ 必要） |
| ベクトル検索 | ChromaDB + intfloat/multilingual-e5-small（384次元） |
| メタデータDB | SQLite（chroma 内蔵） |
| バッチ処理 | Python 3.11+ |
| 音声入力デバイス | Logicool MX Brio（PoC実証済、本番は指向性マイクへ） |

## アーキテクチャ原則

1. オフライン完結：インターネット不要
2. ローカル完結：すべてのデータは端末内
3. 買い切り型：Apache 2.0準拠、ロイヤリティゼロ
4. USB更新運用：CMSレス、USB差し込み30秒更新
5. OSMIL連携：既存表示制御エンジンと協調動作
6. 既存検索UIの温存：AI対話は追加レイヤー

## モデル選定の運用方針

PoC環境（VRAM 8GB以下）と本番ショールーム環境で使い分ける：

| 環境 | モデル | 理由 |
|---|---|---|
| PoC開発（VRAM 6〜8GB / RAM 16〜32GB） | `gemma3:4b`（3.3GB） | 全乗り、warm 3〜4秒、精度6〜7/7 |
| 本番ショールーム（VRAM 16GB+ / RAM 32GB+） | `gemma4:e4b`（9.6GB） | 全乗り時 warm 2〜3秒、精度7/7 |

**実測根拠**：
- gemma4:e4b を VRAM 6GB に乗せると 32%GPU/68%CPU 分割になり、レイテンシ 4〜28秒（σ=10秒）と不安定。
- gemma3:4b は VRAM 6GB 全乗りで 3.3〜4.0秒（σ=0.26秒）と安定。

PoCの判断履歴は `memory/project_argus_canvas_showcase.md` 参照。

## ASR 3層防御アーキテクチャ

Whisper small は日本語カタカナ固有名詞（特に施設名・ブランド名）に弱いため、
3層で固有名詞認識精度を担保する：

| 層 | 場所 | 内容 |
|---|---|---|
| Layer 1: 語彙バイアス | `scripts/voice/transcribe.py` の `initial_prompt` | シーマ固有名詞 86字を Whisper にヒント注入 |
| Layer 2: 後段補正 | `scripts/rag/normalize_transcription.py` | ASR結果のカタカナ語をLevenshtein距離で語彙集と照合（閾値 ratio ≤ 0.30） |
| Layer 3: 検索側ファジー | `scripts/rag/fuzzy_match.py` | DIRECT_RECALL で entity → case_id 解決時に部分一致＋Levenshtein |

実例：「ガーナホテル」「パーナホテル」→ 「ガーナーホテル」（id=113）に補正成功。

新PC（MX Brio + RTX 3060 Ti 8GB）ではASR精度が向上し、Layer 2 はほぼ出動不要。

## Ollama 連携時の注意

- APIエンドポイント：`http://localhost:11434`
- モデル切替：`scripts/voice/classify_intent.py` の `MODEL` 定数で指定
- **タイムアウト**：`OLLAMA_TIMEOUT_SEC = 120.0`（cold start 14〜32秒に対応）
- **Warmup**：`voice_to_intent.py` 起動時にダミー推論で VRAM 事前ロード
- **keep_alive**：Ollama デフォルト 5分。長時間アイドル後は再 cold start
- Thinkingモード：常にOFF（応答速度優先）
- CUDA バージョン：12.x または 13.1 を使用、13.2 は使用禁止
- temperature：0.3（一貫性優先）
- max_tokens：200（インテント分類用）

## end-to-end 性能実測

### Cold start（初回 or 5分アイドル後）
| 段階 | 旧PC（RTX 4050 6GB） | 新PC（RTX 3060 Ti 8GB + MX Brio） |
|---|---|---|
| Whisper 初回ロード | 3秒 | 2.4秒 |
| ChromaDB + e5-small | 13秒 | （遅延ロード） |
| gemma3:4b cold inference | 14〜26秒 | 22〜32秒 |
| end-to-end | 19〜44秒 | 30〜40秒（warmup により短縮可） |

### Warm cycle（直近5分以内）
| 段階 | 旧PC | 新PC |
|---|---|---|
| Whisper ASR | 3秒 | **1.56秒** |
| Layer 2 normalize | 0秒（補正なし） | 0秒（MX Brio効果で補正出動不要） |
| gemma3:4b inference | 4秒 | 3〜4秒（実測待ち） |
| RAG search（e5 warm） | 0.07秒 | 0.05〜0.1秒 |
| **end-to-end total** | **約7秒** | **約5秒（予測）** |

## コーディング規約

### C#（WPF / .NET 8、本番化フェーズ用）
- MVVMパターン、async/await、null安全
- 命名：PascalCase、インターフェースは I プレフィックス
- ファイル名は型名と一致

### Python（バッチ・スクリプト）
- 型ヒント必須
- ruff / black 準拠
- 命名：snake_case
- docstring必須（Google style or NumPy style）

## データ構造

- 事例データ：`data/cases/cima_cases.json`（115件、id=1..115連番、UTF-8 BOM）
- 画像：`data/cases/images/Case_1/`〜`Case_115/`（合計約427MB、git管理外）
- 語彙集：`data/cases/vocabulary.json`（Whisper initial_prompt + Layer 2 候補）
- マニフェスト：`data/cases/manifest.json`
- 来歴記録：`data/cases/PROVENANCE.md`
- システムプロンプト：`data/prompts/intent_classification_v1.md`
- ChromaDB：`data/cases/chroma_db/`（`scripts/rag/build_index.py` で再生成可、git管理外）

## 禁止事項

- localStorage / sessionStorage（ブラウザストレージ）の利用
- 外部APIへの依存（完全ローカル動作のため）
- シーマ・アーガス以外の競合企業情報の組込
- 「Gemma」名を製品名・UI文言に使用（Apache 2.0商標条項、内部メモは可）
- 政治・宗教評価への踏み込み
- 個人情報のログ保持（音声・テキストともセッション終了で破棄）

## 文体・ブランディング規約

### UI文言
- 「です・ます調」統一
- 「お客様」ではなく「来場者」または「ご来館の皆様」
- 専門用語は初出時に平易な言い換えを添える

### コメント・ドキュメント
- 日本語コメント可（社内利用前提）
- TODO/FIXME は英語＋日本語併記推奨
- コミットメッセージは英語（Public リポジトリのため）

## 環境セットアップ

### Windows 必須ソフト
1. **Python 3.11+**（PoCは 3.13 で動作確認済）
2. **Ollama**：https://ollama.com/download/windows
3. **FFmpeg**：`winget install Gyan.FFmpeg`（Whisper の WAV デコード用）
4. **管理者権限 PowerShell**：`keyboard` パッケージが低レベルキーフックを張るため必須

### モデル取得
```
ollama pull gemma3:4b
python -c "import whisper; whisper.load_model('small')"
```

### ChromaDB 構築
```
python scripts/rag/build_index.py
```

## 開発フロー

1. 機能ブランチを切る：`feature/<short-name>`
2. Claude Codeで実装
3. 動作確認（`python scripts/voice/voice_to_intent.py --once`）
4. プルリクエスト作成（Public リポジトリ）
5. レビュー → main マージ

## 関連ドキュメント

- 要件定義書 v0.3：`docs/requirements/v0.3_showcase_requirements.md`
- 体験フロー：`docs/requirements/v0.3_experience_flow.md`
- プロンプト設計：`docs/architecture/prompt_design.md`
- 事例データスキーマ：`docs/architecture/case_schema.md`
- データ来歴：`data/cases/PROVENANCE.md`
