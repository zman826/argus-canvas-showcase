# data/cases/ 由来

Argus Canvas Showcase のシーマ社事例データの来歴記録。

## 受領データ

| 配置パス | 元名称 | 提供元 | 受領日 | 件数 |
|---|---|---|---|---|
| `cima_cases.json` | `info.json` | シーマ | 2026-05-14 | 115件（id=1..115 連番） |
| `images/Case_1/` 〜 `images/Case_115/` | 同名 | シーマ | 2026-05-14 | 各フォルダに mainPhoto + subPhoto |

## データスキーマ

`cima_cases.json` の各 case は以下のフィールドを持つ：

| field | 型 | 説明 |
|---|---|---|
| `id` | int | 1〜115 の連番 |
| `title` | str | 事例タイトル |
| `subTitle` | str | サブタイトル |
| `ex` | str | 本文（改行含む、年月情報を含むことがある） |
| `tag` | list[str] | タグ（単数形、※ "tags" ではなく "tag"） |
| `mainPhoto` | str | メイン画像のファイル名（パス情報なし） |
| `subPhoto` | list[str] | サブ画像のファイル名リスト |

エンコーディングは **UTF-8 with BOM**。ローダは `encoding="utf-8-sig"` で読み込むこと。

## 画像ファイルの解決

`mainPhoto` / `subPhoto` はファイル名のみで、ディレクトリ情報を持たない。
`images/Case_*/` 配下を再帰スキャンしてファイル名一致で実パス解決を行う。

`scripts/rag/load_data.py:build_image_manifest()` が `manifest.json` を生成し、
`{case_id: {mainPhoto_path, subPhoto_paths, folder}}` をキャッシュする。

**Case_N の N と id の対応**: 実測 111/115 件で一致。残り4件は不一致だが、
ファイル名ベース解決のため運用上問題なし。

## tag 値の集合（受領時点で確定）

| tag | 件数 |
|---|---|
| イベント | 64 |
| システム | 37 |
| プロジェクションマッピング | 34 |
| LEDビジョン | 30 |
| KAIROS | 13 |
| 展示会 | 9 |
| 大阪・関西万博 | 8 |

## 自動生成ファイル（gitignore 対象）

| ファイル | 役割 | 生成スクリプト |
|---|---|---|
| `manifest.json` | 画像ファイル名→実パス解決マップ | `scripts/rag/load_data.py` |
| `vocabulary.json` | 固有名詞集 + Whisper initial_prompt | `scripts/rag/load_data.py` |
| `chroma_db/` | ChromaDB 永続化ディレクトリ | `scripts/rag/build_index.py` |

これらは `cima_cases.json` から再生成可能のため、Git 追跡対象外。

## 機密扱い

- `cima_cases.json` 本体: 顧客名・施工内容を含むため Git 追跡しない（`.gitignore: data/cases/*.json`）
- 画像ファイル群: 顧客現場写真のため Git 追跡しない（`.gitignore: data/cases/images/`）
- 本ファイル（PROVENANCE.md）: 個別案件詳細を含まないため Git 追跡する
