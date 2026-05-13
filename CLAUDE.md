# Argus Canvas Showcase 開発ガイド

## プロジェクト概要

シーマ社の事例検索サイネージ「Argus Canvas Showcase」。
Gemma 4をローカル動作させ、音声駆動でシーマの導入事例ページを
即時表示するWindowsアプリです。

**目的**：シーマショールーム来訪客に対し、音声入力で関連事例を
即座に呼び出し、大型ディスプレイで提示する営業デモツール。

## 作業環境

- 開発フォルダ：E:\GppgleDrive_new\claude\argus-canvas-showcase
- 親フォルダ（Google Drive同期）：E:\GppgleDrive_new\claude

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
| UI層 | WPF / .NET 8 |
| AI推論 | Ollama + Gemma 4 E4B（標準）／26B A4B（高品質オプション） |
| ベクトル検索 | ChromaDB |
| メタデータDB | SQLite |
| バッチ処理 | Python 3.11+ |
| 音声入出力 | Windows Speech API（ASR）／VOICEVOX（TTS、オプション） |

## アーキテクチャ原則

1. オフライン完結：インターネット不要
2. ローカル完結：すべてのデータは端末内
3. 買い切り型：Apache 2.0準拠、ロイヤリティゼロ
4. USB更新運用：CMSレス、USB差し込み30秒更新
5. OSMIL連携：既存表示制御エンジンと協調動作
6. 既存検索UIの温存：AI対話は追加レイヤー

## コーディング規約

### C#（WPF / .NET 8）
- MVVMパターン、async/await、null安全
- 命名：PascalCase、インターフェースは I プレフィックス
- ファイル名は型名と一致

### Python（バッチ・スクリプト）
- 型ヒント必須
- ruff / black 準拠
- 命名：snake_case
- docstring必須

## Gemma 4 連携時の注意

- APIエンドポイント：http://localhost:11434
- モデル指定：
  - 標準：gemma4:e4b
  - 高品質オプション：gemma4:26b-a4b
- Thinkingモード：常にOFF（応答速度優先）
- CUDA バージョン：12.x または 13.1 を使用、13.2 は使用禁止
- temperature：0.3（一貫性優先）
- max_tokens：600

## データ構造

- 事例データ：data/cases/*.json
- システムプロンプト：data/prompts/*.md
- テストデータ：data/test_cases/*.json

## 禁止事項

- localStorage / sessionStorage（ブラウザストレージ）の利用
- 外部APIへの依存（完全ローカル動作のため）
- シーマ・アーガス以外の競合企業情報の組込
- 「Gemma」名を製品名・UI文言に使用（Apache 2.0商標条項）
- 政治・宗教評価への踏み込み
- 個人情報のログ保持

## 文体・ブランディング規約

### UI文言
- 「です・ます調」統一
- 「お客様」ではなく「来場者」または「ご来館の皆様」
- 専門用語は初出時に平易な言い換えを添える

### コメント・ドキュメント
- 日本語コメント可（社内利用前提）
- TODO/FIXME は英語＋日本語併記推奨

## 開発フロー

1. 機能ブランチを切る：feature/<short-name>
2. Claude Codeで実装
3. ユニットテスト追加（カバレッジ80%目標）
4. プルリクエスト作成
5. 人手レビュー
6. mainマージ

## 関連ドキュメント

- 要件定義書 v0.3：docs/requirements/v0.3_showcase_requirements.md
- 体験フロー：docs/requirements/v0.3_experience_flow.md
- プロンプト設計：docs/architecture/prompt_design.md
- 事例データスキーマ：docs/architecture/case_schema.md
