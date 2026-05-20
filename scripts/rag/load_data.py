"""シーマ事例データ (cima_cases.json) のロードと画像マニフェスト構築.

シーマから受領した `cima_cases.json` (UTF-8 with BOM) と Case_*/ 画像フォルダ群を
読み込み、以下を提供する:

- `load_cases()`: 115件の事例データを list[dict] で返す
- `find_cima_data_dir()`: cima_cases.json の親ディレクトリを探索（worktree → main project へ walk-up）
- `build_image_manifest()`: ファイル名ベースで mainPhoto/subPhoto の実パスを解決
- `extract_proper_nouns()`: 全 title から固有名詞候補（カタカナ4+/英大3+）抽出
- `extract_tag_set()`: 全 tag の集合
- `build_whisper_prompt()`: Whisper initial_prompt 用語彙文字列生成
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

CASES_FILENAME: str = "cima_cases.json"
IMAGES_DIRNAME: str = "images"
MANIFEST_FILENAME: str = "manifest.json"
VOCABULARY_FILENAME: str = "vocabulary.json"

# title 内の facility 系キーワード辞書（タイトルに含まれていれば対応 facility_type を付与）
# tag フィールドは技術／イベント種別に偏っているため、facility は title 解析で判定する。
FACILITY_KEYWORDS: dict[str, list[str]] = {
    "hotel": ["ホテル"],
    "school": ["学校", "中学", "高校", "大学", "学園"],
    "expo": ["万博", "EXPO", "Expo"],
    "exhibition": ["展", "出展", "ブース", "ショー", "Show", "SHOP"],
    "showroom": ["ショールーム"],
    "museum": ["美術館", "博物館", "ギャラリー"],
    "station": ["駅"],
    "pavilion": ["パビリオン"],
    "hall": ["ホール"],
    "event": ["イベント", "ライブ", "コンサート", "パーティー", "フェスタ", "祭"],
    "store": ["店舗", "ショップ"],
}

# Whisper initial_prompt に必ず含めたいドメイン用語（最優先）
# Whisper は長い prompt で多言語ハルシネーションを起こすため、本当に必要な語のみ
DOMAIN_TERMS_REQUIRED: list[str] = [
    "シーマ",
    "LEDビジョン", "プロジェクションマッピング", "KAIROS",
    "大阪・関西万博",
    "ガーナーホテル", "セネガルパビリオン", "コマツ", "新宿駅",
]

_KATAKANA_RE = re.compile(r"[ァ-ヴー]{3,}")
_UPPER_RE = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}\b")


def find_cima_data_dir() -> Path:
    """`cima_cases.json` が置かれているディレクトリを探索する.

    優先順位:
        1. 環境変数 `CIMA_DATA_DIR`
        2. このファイルからの ancestor 探索（worktree → main project）

    Returns:
        cima_cases.json が存在するディレクトリ（通常は <project>/data/cases）。

    Raises:
        FileNotFoundError: どこにも見つからない場合。
    """
    env = os.environ.get("CIMA_DATA_DIR")
    if env:
        p = Path(env)
        if (p / CASES_FILENAME).exists():
            return p.resolve()
        raise FileNotFoundError(
            f"CIMA_DATA_DIR={env} に {CASES_FILENAME} が見つかりません"
        )

    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        candidate = ancestor / "data" / "cases" / CASES_FILENAME
        if candidate.exists():
            return candidate.parent

    raise FileNotFoundError(
        f"{CASES_FILENAME} が見つかりません。CIMA_DATA_DIR を設定するか、"
        f"<project>/data/cases/ に配置してください。"
    )


def load_cases(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """`cima_cases.json` を UTF-8 with BOM 対応で読み込む.

    Args:
        data_dir: cima_cases.json が置かれているディレクトリ。None なら自動探索。

    Returns:
        115件の事例 dict のリスト。各 dict は id/title/subTitle/ex/tag/mainPhoto/subPhoto。

    Raises:
        FileNotFoundError: ファイルが存在しない。
        json.JSONDecodeError: JSON パース失敗。
        ValueError: 必須フィールド欠損。
    """
    if data_dir is None:
        data_dir = find_cima_data_dir()
    cases_path = data_dir / CASES_FILENAME
    raw = cases_path.read_text(encoding="utf-8-sig")  # BOM 対応
    cases = json.loads(raw)

    required = {"id", "title", "subTitle", "ex", "tag", "mainPhoto", "subPhoto"}
    for c in cases:
        missing = required - c.keys()
        if missing:
            raise ValueError(f"id={c.get('id')} に必須フィールド欠損: {missing}")

    return cases


def build_image_manifest(
    cases: list[dict[str, Any]],
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """各 case の mainPhoto / subPhoto をファイル名で images/ から解決する.

    Case_N フォルダの N と id が一致するかに関わらず、ファイル名ベースで
    全 images/Case_*/ を再帰スキャンして実パスを解決する。

    Args:
        cases: load_cases() の結果。
        data_dir: cima_cases.json のディレクトリ。None なら自動探索。

    Returns:
        {
            "by_id": {id: {"main": path_or_None, "subs": [path, ...], "folder": Case_N or None}},
            "missing": [{"id": int, "filename": str, "kind": "main"|"sub"}, ...],
            "duplicates": [filename, ...],  # 複数の Case_* に同名ファイルがある場合
            "case_folder_mapping": {id: Case_N},  # 解決できた範囲で
        }
    """
    if data_dir is None:
        data_dir = find_cima_data_dir()
    images_dir = data_dir / IMAGES_DIRNAME
    if not images_dir.exists():
        raise FileNotFoundError(f"画像ディレクトリが見つかりません: {images_dir}")

    # ファイル名 → 出現パス（複数ありえる）のインデックスを作る
    filename_index: dict[str, list[Path]] = {}
    for f in images_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            filename_index.setdefault(f.name, []).append(f)

    by_id: dict[int, dict[str, Any]] = {}
    missing: list[dict[str, Any]] = []
    duplicates: set[str] = set()
    case_folder_mapping: dict[int, str] = {}

    def resolve(fname: str, case_id: int, kind: str) -> Path | None:
        paths = filename_index.get(fname)
        if not paths:
            missing.append({"id": case_id, "filename": fname, "kind": kind})
            return None
        if len(paths) > 1:
            duplicates.add(fname)
        return paths[0]

    for c in cases:
        cid = c["id"]
        main_path = resolve(c["mainPhoto"], cid, "main")
        sub_paths = [resolve(s, cid, "sub") for s in c.get("subPhoto", [])]
        sub_paths_resolved = [p for p in sub_paths if p is not None]

        folder = None
        if main_path is not None:
            # Case_N フォルダ名を main の親から取得
            parent_name = main_path.parent.name
            if parent_name.startswith("Case_"):
                folder = parent_name
                case_folder_mapping[cid] = folder

        by_id[cid] = {
            "main": str(main_path) if main_path else None,
            "subs": [str(p) for p in sub_paths_resolved],
            "folder": folder,
        }

    return {
        "by_id": by_id,
        "missing": missing,
        "duplicates": sorted(duplicates),
        "case_folder_mapping": case_folder_mapping,
    }


def save_manifest(manifest: dict[str, Any], data_dir: Path | None = None) -> Path:
    """マニフェストを `data/cases/manifest.json` に保存する.

    Args:
        manifest: build_image_manifest() の結果。
        data_dir: 保存先ディレクトリ。None なら自動探索。

    Returns:
        保存先のパス。
    """
    if data_dir is None:
        data_dir = find_cima_data_dir()
    out = data_dir / MANIFEST_FILENAME
    out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def extract_proper_nouns(cases: list[dict[str, Any]]) -> Counter[str]:
    """全 title / subTitle から固有名詞候補を抽出（カタカナ3文字以上 / 英大文字+小文字混在3文字以上）.

    Args:
        cases: load_cases() の結果。

    Returns:
        {固有名詞文字列: 出現件数} の Counter（多い順に並べたいときは most_common）。
    """
    counter: Counter[str] = Counter()
    for c in cases:
        for field in ("title", "subTitle"):
            text = c.get(field, "")
            for m in _KATAKANA_RE.findall(text):
                counter[m] += 1
            for m in _UPPER_RE.findall(text):
                counter[m] += 1
    return counter


def extract_tag_set(cases: list[dict[str, Any]]) -> Counter[str]:
    """全 tag の出現頻度を返す.

    Args:
        cases: load_cases() の結果。

    Returns:
        {tag: 件数} の Counter。
    """
    counter: Counter[str] = Counter()
    for c in cases:
        for t in c.get("tag", []):
            counter[t] += 1
    return counter


def build_whisper_prompt(
    cases: list[dict[str, Any]],
    max_chars: int = 90,
) -> str:
    """Whisper `initial_prompt` 用の語彙ヒント文字列を生成する.

    Whisper は initial_prompt の語彙を優先的に出力に取り込むが、長すぎる
    （244 token 超）と多言語ハルシネーション・速度低下を起こす。
    日本語で 80〜100 字を目安に、最重要語のみ詰める。

    優先順位:
        1. DOMAIN_TERMS_REQUIRED（シーマ、LEDビジョン等の必須語）
        2. 全 tag（7種）
        3. 頻度上位の固有名詞（カタカナ/英大）

    Args:
        cases: load_cases() の結果。
        max_chars: 最大文字数（推奨 90 以下。これを超えると 244 token 上限に近づき
            Whisper が不安定化する）。

    Returns:
        カンマ区切りの語彙文字列（末尾に句点）。
    """
    chosen: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> bool:
        """語を追加し、文字数制限を超えたら False。"""
        if term in seen:
            return True
        chosen.append(term)
        seen.add(term)
        # 区切り文字「、」+語の長さ で計算
        total = sum(len(t) for t in chosen) + len(chosen) - 1  # 「、」区切り
        if total > max_chars:
            chosen.pop()
            seen.discard(term)
            return False
        return True

    # 1. 必須ドメイン語
    for term in DOMAIN_TERMS_REQUIRED:
        if not add(term):
            break

    # 2. 全 tag（7種、すべて入る）
    for tag, _ in extract_tag_set(cases).most_common():
        if not add(tag):
            break

    # 3. 頻度上位の固有名詞
    proper_nouns = extract_proper_nouns(cases)
    for noun, _ in proper_nouns.most_common():
        if not add(noun):
            break

    return "、".join(chosen) + "。"


def build_vocabulary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """正規化・検索で使う語彙データを構築する.

    後段の normalize_transcription.py（Layer 2）と fuzzy_match.py（Layer 3）が
    この vocabulary を参照して誤認識の補正・固有名詞マッチを行う。

    Args:
        cases: load_cases() の結果。

    Returns:
        {
            "proper_nouns": [str, ...],         # 全固有名詞候補（重複なし、頻度降順）
            "tags": [str, ...],                  # 全 tag（7種）
            "case_titles": [{"id": int, "title": str}, ...],  # 全件
            "title_proper_nouns": {id: [str, ...]},  # case 別の固有名詞候補
            "whisper_initial_prompt": str,      # Whisper 用語彙文字列
        }
    """
    proper = extract_proper_nouns(cases)
    tags = extract_tag_set(cases)

    title_pn: dict[int, list[str]] = {}
    for c in cases:
        found: list[str] = []
        for m in _KATAKANA_RE.findall(c["title"]):
            if m not in found:
                found.append(m)
        for m in _UPPER_RE.findall(c["title"]):
            if m not in found:
                found.append(m)
        title_pn[c["id"]] = found

    return {
        "proper_nouns": [n for n, _ in proper.most_common()],
        "tags": [t for t, _ in tags.most_common()],
        "case_titles": [{"id": c["id"], "title": c["title"]} for c in cases],
        "title_proper_nouns": title_pn,
        "whisper_initial_prompt": build_whisper_prompt(cases),
    }


def save_vocabulary(vocab: dict[str, Any], data_dir: Path | None = None) -> Path:
    """vocabulary を `data/cases/vocabulary.json` に保存する.

    Args:
        vocab: build_vocabulary() の結果。
        data_dir: 保存先ディレクトリ。None なら自動探索。

    Returns:
        保存先のパス。
    """
    if data_dir is None:
        data_dir = find_cima_data_dir()
    out = data_dir / VOCABULARY_FILENAME
    out.write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def load_vocabulary(data_dir: Path | None = None) -> dict[str, Any]:
    """保存済み vocabulary.json をロードする（無ければ build して保存）.

    Args:
        data_dir: vocabulary.json があるディレクトリ。None なら自動探索。

    Returns:
        vocabulary dict。
    """
    if data_dir is None:
        data_dir = find_cima_data_dir()
    path = data_dir / VOCABULARY_FILENAME
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    cases = load_cases(data_dir)
    vocab = build_vocabulary(cases)
    save_vocabulary(vocab, data_dir)
    return vocab


if __name__ == "__main__":
    # 単体動作確認 + manifest / vocabulary 生成
    data_dir = find_cima_data_dir()
    print(f"[load_data] data_dir = {data_dir}")

    cases = load_cases(data_dir)
    print(f"[load_data] {len(cases)} 件ロード（id={min(c['id'] for c in cases)}..{max(c['id'] for c in cases)}）")

    print("\n[load_data] 画像マニフェスト構築中...")
    manifest = build_image_manifest(cases, data_dir)
    print(f"  解決済み: {len(manifest['by_id'])} 件")
    print(f"  欠損: {len(manifest['missing'])} 件")
    print(f"  ファイル名重複: {len(manifest['duplicates'])} 件")
    if manifest["missing"]:
        print(f"  最初の3件: {manifest['missing'][:3]}")
    if manifest["duplicates"]:
        print(f"  重複ファイル名: {manifest['duplicates'][:5]}")

    # case_folder_mapping を分析
    cf = manifest["case_folder_mapping"]
    matches = sum(1 for cid, folder in cf.items() if folder == f"Case_{cid}")
    print(f"\n  Case_N == id 仮説検証: {matches} / {len(cf)} 件が一致")

    save_manifest(manifest, data_dir)
    print(f"  → {data_dir / MANIFEST_FILENAME}")

    print("\n[load_data] vocabulary 構築中...")
    vocab = build_vocabulary(cases)
    print(f"  proper_nouns: {len(vocab['proper_nouns'])} 語")
    print(f"  tags: {vocab['tags']}")
    print(f"  whisper_initial_prompt 長: {len(vocab['whisper_initial_prompt'])} 字")
    print(f"  whisper_initial_prompt:\n    {vocab['whisper_initial_prompt']}")
    save_vocabulary(vocab, data_dir)
    print(f"  → {data_dir / VOCABULARY_FILENAME}")
