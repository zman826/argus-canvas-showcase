# 事例データ JSONスキーマ定義

| 項目 | 内容 |
|---|---|
| 文書番号 | ARCH-2026-001 |
| 作成日 | 2026-05-13 |
| 作成者 | 株式会社アーガス企画 |
| 関連文書 | [要件定義書 v0.3](../requirements/v0.3_showcase_requirements.md) |

---

## 1. 概要

`data/cases/` 配下に配置するシーマ事例データのJSONフォーマットを定義する。
1ファイル1事例とし、ファイル名は `{id}.json`（例：`CIMA-18433.json`）とする。

バッチ処理（`scripts/poc/`）がシーマWebサイトから収集し、このスキーマに沿って
生成する。生成後、`Showcase.Data` がSQLiteおよびChromaDBへインポートする。

---

## 2. フィールド定義

### 2.1 識別・参照

| フィールド名 | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✅ | 事例ID（例: `"CIMA-18433"`）。シーマWebのページIDに準拠 |
| `url` | string | ✅ | シーマWebの事例ページURL |

### 2.2 基本情報

| フィールド名 | 型 | 必須 | 説明 |
|---|---|---|---|
| `title_ja` | string | ✅ | 事例タイトル（日本語） |
| `client_name` | string | ✅ | 施主名（例: `"川崎水族館（カワスイ）"`） |
| `client_type` | enum | ✅ | 施設種別（後述） |
| `year` | integer | ✅ | 施工年（西暦） |
| `month` | integer | ✅ | 施工月（1〜12）。不明な場合は `0` |

**`client_type` 列挙値**

| 値 | 説明 |
|---|---|
| `hotel` | ホテル・旅館 |
| `commercial` | 商業施設（ショッピングモール等） |
| `museum` | 博物館・美術館 |
| `school` | 学校・教育機関 |
| `station` | 駅・交通施設 |
| `stadium` | 競技場・アリーナ |
| `showroom` | ショールーム・展示施設 |
| `shrine` | 寺社・宗教施設 |
| `aquarium` | 水族館 |
| `mansion_gallery` | マンションギャラリー |
| `other` | その他 |

### 2.3 分類・環境

| フィールド名 | 型 | 必須 | 説明 |
|---|---|---|---|
| `category_primary` | enum | ✅ | 主カテゴリ |
| `category_secondary` | enum | ✅ | 副カテゴリ（製品種別） |
| `indoor_outdoor` | enum | ✅ | 設置環境 |
| `location_type` | string | ✅ | 設置場所の詳細（例: `"lobby"`, `"entrance"`, `"main_hall"`） |
| `use_case_tags` | array[string] | ✅ | 用途タグ（複数可） |

**`category_primary` 列挙値**

| 値 | 説明 |
|---|---|
| `installation` | 常設インストール |
| `event` | イベント・期間限定 |
| `exhibition` | 展示・展覧会 |

**`category_secondary` 列挙値**

| 値 | 説明 |
|---|---|
| `led_vision` | LEDビジョン |
| `audio_system` | 音響システム |
| `lighting` | 照明 |
| `control_system` | 映像・制御システム |

**`indoor_outdoor` 列挙値**

| 値 | 説明 |
|---|---|
| `indoor` | 屋内 |
| `outdoor` | 屋外 |
| `semi_outdoor` | 半屋外（軒下・屋根付き等） |

### 2.4 製品情報

| フィールド名 | 型 | 必須 | 説明 |
|---|---|---|---|
| `products` | array[Product] | ✅ | 使用製品リスト（1件以上） |

**Product オブジェクト**

| フィールド名 | 型 | 必須 | 説明 |
|---|---|---|---|
| `type` | string | ✅ | 製品種別（例: `"LEDビジョン"`, `"COB LEDビジョン"`） |
| `name` | string | ✅ | 製品名・型番（例: `"P1.9 フルカラーLEDビジョン"`） |
| `pitch_mm` | number | - | LEDピッチ（mm単位。LEDビジョン以外は `null`） |
| `features` | array[string] | - | 製品特徴タグ（例: `["高輝度", "耐水", "COB"]`） |

### 2.5 コンテンツ・説明

| フィールド名 | 型 | 必須 | 説明 |
|---|---|---|---|
| `summary_short` | string | ✅ | 短い要約（100文字以内）。検索結果一覧・音声読み上げで使用 |
| `summary_long` | string | ✅ | 詳細説明（500文字程度）。事例詳細ページで使用 |
| `staff_comment` | string | - | 担当スタッフのコメント |
| `staff_name` | string | - | 担当スタッフ名 |
| `staff_department` | string | - | 担当スタッフ所属部門 |

### 2.6 ショールーム・関連情報

| フィールド名 | 型 | 必須 | 説明 |
|---|---|---|---|
| `showroom_visitable` | boolean | ✅ | ショールームで実機確認可能かどうか |
| `related_cases` | array[string] | ✅ | 関連事例IDリスト（空配列も可） |
| `keywords_for_voice` | array[string] | ✅ | 音声検索用キーワード（5〜10個）。施主名の読み方・別称を含める |

---

## 3. JSONサンプル：川崎水族館（カワスイ）事例

```json
{
  "id": "CIMA-18433",
  "url": "https://www.cima.co.jp/cases/18433",
  "title_ja": "川崎水族館（カワスイ）エントランスLEDビジョン設置事例",
  "client_name": "川崎水族館（カワスイ）",
  "client_type": "aquarium",
  "year": 2020,
  "month": 7,
  "category_primary": "installation",
  "category_secondary": "led_vision",
  "indoor_outdoor": "indoor",
  "location_type": "entrance",
  "use_case_tags": ["水族館", "エントランス", "集客", "サイネージ", "フルカラー"],
  "products": [
    {
      "type": "COB LEDビジョン",
      "name": "P1.9 フルカラーCOB LEDビジョン",
      "pitch_mm": 1.9,
      "features": ["COB", "高精細", "屋内対応", "高輝度"]
    }
  ],
  "summary_short": "川崎水族館エントランスにP1.9のCOB LEDビジョンを設置。来館者を迎える迫力ある映像演出を実現。",
  "summary_long": "川崎市にある「川崎水族館（カワスイ）」のエントランスに、P1.9ミリピッチのCOB LEDビジョンを設置した事例です。COB（Chip On Board）方式を採用することで、従来のSMD方式と比べて画素が均一で高精細な映像を実現しています。エントランスという来館者が最初に目にする場所に設置されており、水中をイメージした映像コンテンツを常時放映することで、水族館のブランドイメージ向上と集客効果に貢献しています。シーマが設計から施工・調整まで一括対応し、納期・品質ともにご満足いただいております。",
  "staff_comment": "エントランスという重要なロケーションにCOBタイプを採用いただいたことで、高精細かつ均一な映像を実現できました。水族館の世界観と映像が一体化した空間になっていると思います。",
  "staff_name": "田中 太郎",
  "staff_department": "映像システム事業部",
  "showroom_visitable": false,
  "related_cases": ["CIMA-17892", "CIMA-19201", "CIMA-16445"],
  "keywords_for_voice": [
    "カワスイ",
    "川崎水族館",
    "かわさきすいぞくかん",
    "水族館",
    "COB",
    "エントランス",
    "川崎",
    "P1.9",
    "フルカラー"
  ]
}
```

---

## 4. バリデーションルール

| ルール | 内容 |
|---|---|
| `id` | `CIMA-` プレフィックス必須、数字5桁以上 |
| `url` | https:// で始まる有効なURL |
| `year` | 2000〜現在年の整数 |
| `month` | 0〜12の整数（0は月不明） |
| `summary_short` | 100文字以内 |
| `keywords_for_voice` | 5〜10個のstring |
| `pitch_mm` | LEDビジョン系のproductでは必須。0.5〜20.0の範囲 |
| `related_cases` | 実在する `id` のみ（バッチ処理でクロスチェック） |

---

## 5. サンプルデータファイル

Gitリポジトリには `data/cases/sample_*.json` のみコミット可。
実際の事例データ（`data/cases/CIMA-*.json`）は `.gitignore` 対象。

```
data/cases/
├── sample_hotel.json        # ホテル事例サンプル
├── sample_aquarium.json     # 水族館事例サンプル（カワスイ参考）
└── CIMA-18433.json          # 実データ（gitignore対象）
```

---

## 6. 関連ドキュメント

- 要件定義書：[../requirements/v0.3_showcase_requirements.md](../requirements/v0.3_showcase_requirements.md)
- 体験フロー：[../requirements/v0.3_experience_flow.md](../requirements/v0.3_experience_flow.md)
- プロンプト設計：[prompt_design.md](prompt_design.md)
