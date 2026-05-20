"""ChromaDB ベクトル索引の構築.

`cima_cases.json` 全115件を multilingual-e5-small で埋め込み、
ChromaDB の persistent collection として保存する。

- 埋め込みモデル: intfloat/multilingual-e5-small（~470MB、初回ダウンロード）
- e5 系の規約: passage は "passage: " プレフィックス、query は "query: " プレフィックス
- 距離関数: cosine
- 保存先: <data_dir>/chroma_db/

実行:
    python build_index.py             # 全件再構築
    python build_index.py --force     # 既存 collection を削除して再構築
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from extract_metadata import (
    build_searchable_text,
    extract_all_metadata,
)
from load_data import find_cima_data_dir, load_cases

COLLECTION_NAME: str = "cima_cases"
EMBEDDING_MODEL_NAME: str = "intfloat/multilingual-e5-small"
CHROMA_DIRNAME: str = "chroma_db"

# 全 tag を bool フラグ化するためのマッピング（cima_cases.json 解析で確定した 7種）
TAG_FLAG_MAPPING: dict[str, str] = {
    "イベント": "tag_event",
    "システム": "tag_system",
    "プロジェクションマッピング": "tag_projection_mapping",
    "LEDビジョン": "tag_led_vision",
    "KAIROS": "tag_kairos",
    "展示会": "tag_exhibition",
    "大阪・関西万博": "tag_osaka_kansai_expo",
}

# 全 facility_type を bool フラグ化（FACILITY_KEYWORDS のキー集合）
FACILITY_FLAG_PREFIX: str = "facility_"

_EMBEDDING_MODEL = None  # 遅延ロード（モジュール import 時に重い初期化を避ける）


def get_embedding_model() -> Any:
    """埋め込みモデル（sentence-transformers）をロードし、モジュール内でキャッシュする.

    Returns:
        SentenceTransformer インスタンス。
    """
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        from sentence_transformers import SentenceTransformer
        print(f"[build_index] 埋め込みモデルロード中: {EMBEDDING_MODEL_NAME}")
        t0 = time.time()
        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print(f"[build_index]   ロード完了 ({time.time() - t0:.1f}秒)")
    return _EMBEDDING_MODEL


def encode_passages(texts: list[str]) -> list[list[float]]:
    """passage プレフィックスを付与して埋め込みベクトルを生成する.

    Args:
        texts: 埋め込み対象テキスト群（プレフィックスは付けず、内側で付与）。
            ※ extract_metadata.build_searchable_text() が既に "passage: " を
              付与している場合は二重付与を防ぐため、ここでは付与しない設計とする。

    Returns:
        埋め込みベクトル（normalized）の list。
    """
    model = get_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    return embeddings.tolist()


def encode_query(query: str) -> list[float]:
    """query プレフィックスを付与して1件の埋め込みベクトルを返す.

    Args:
        query: ユーザークエリ文字列（"query: " プレフィックスは内側で付与）。

    Returns:
        正規化済み埋め込みベクトル。
    """
    model = get_embedding_model()
    text = f"query: {query}"
    emb = model.encode(text, normalize_embeddings=True)
    return emb.tolist()


def build_chroma_metadata(case: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """ChromaDB 用の filter 可能メタデータを構築する.

    ChromaDB の metadata は str/int/float/bool のみ。list は CSV 化。
    検索効率のため、全 tag と全 facility_type を bool フラグに展開する。

    Args:
        case: 元 case dict。
        meta: extract_metadata() の結果。

    Returns:
        ChromaDB metadata dict。
    """
    md: dict[str, Any] = {
        "id": meta["id"],
        "title": case["title"],
        "year": meta["year"] if meta["year"] is not None else 0,
        "year_known": meta["year"] is not None,
        "primary_facility_type": meta["primary_facility_type"],
        "indoor_outdoor": meta["indoor_outdoor"] or "",
        "has_pitch": meta["has_pitch"],
        "pitch_values_csv": meta["pitch_values_csv"],
        "has_4k": meta["has_4k"],
        "has_8k": meta["has_8k"],
        "tags_csv": meta["tags_csv"],
        "facility_types_csv": meta["facility_types_csv"],
        "proper_nouns_csv": meta["proper_nouns_csv"],
    }
    # tag フラグ化
    case_tags = set(case.get("tag", []))
    for tag, flag_name in TAG_FLAG_MAPPING.items():
        md[flag_name] = tag in case_tags
    # facility フラグ化
    case_facilities = set(meta["facility_types_csv"].split(",")) if meta["facility_types_csv"] else set()
    for ftype in [
        "hotel", "school", "expo", "exhibition", "showroom", "museum",
        "station", "pavilion", "hall", "event", "store", "other",
    ]:
        md[f"{FACILITY_FLAG_PREFIX}{ftype}"] = ftype in case_facilities
    return md


def build_index(force: bool = False) -> dict[str, Any]:
    """115件全 case を embedding 化して ChromaDB collection に投入する.

    Args:
        force: True なら既存 collection を削除してから再構築。

    Returns:
        {
            "added": int,
            "collection_name": str,
            "persist_directory": str,
            "embedding_dim": int,
            "elapsed_sec": float,
        }
    """
    import chromadb

    t0 = time.time()
    data_dir = find_cima_data_dir()
    chroma_dir = data_dir / CHROMA_DIRNAME

    cases = load_cases(data_dir)
    print(f"[build_index] {len(cases)} 件 ロード（id={min(c['id'] for c in cases)}..{max(c['id'] for c in cases)}）")

    metas = extract_all_metadata(cases)

    print(f"[build_index] 埋め込みテキスト生成中...")
    passage_texts = [build_searchable_text(c) for c in cases]

    print(f"[build_index] 埋め込み計算中（{len(passage_texts)} 件）...")
    # build_searchable_text は既に "passage: " プレフィックスを含むので、再付与なし
    embeddings = encode_passages(passage_texts)
    embedding_dim = len(embeddings[0]) if embeddings else 0

    print(f"[build_index] ChromaDB 接続中: {chroma_dir}")
    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))

    if force:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"[build_index]   既存 collection 削除")
        except Exception:  # noqa: BLE001 - collection が無い場合のエラー型は実装依存
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    if collection.count() > 0 and not force:
        print(f"[build_index] 既に {collection.count()} 件入っています。"
              f"--force で再構築できます。スキップします。")
        return {
            "added": 0,
            "collection_name": COLLECTION_NAME,
            "persist_directory": str(chroma_dir),
            "embedding_dim": embedding_dim,
            "elapsed_sec": round(time.time() - t0, 2),
        }

    metadatas = [build_chroma_metadata(c, m) for c, m in zip(cases, metas)]
    ids = [str(c["id"]) for c in cases]

    collection.add(
        ids=ids,
        documents=passage_texts,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    elapsed = time.time() - t0
    print(f"[build_index] 完了: {len(ids)} 件追加 ({elapsed:.1f}秒)")
    return {
        "added": len(ids),
        "collection_name": COLLECTION_NAME,
        "persist_directory": str(chroma_dir),
        "embedding_dim": embedding_dim,
        "elapsed_sec": round(elapsed, 2),
    }


def get_collection() -> Any:
    """既存 collection をオープンする（search 側で利用）.

    Returns:
        chromadb.Collection。
    """
    import chromadb

    data_dir = find_cima_data_dir()
    chroma_dir = data_dir / CHROMA_DIRNAME
    client = chromadb.PersistentClient(path=str(chroma_dir))
    return client.get_collection(COLLECTION_NAME)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="シーマ事例 ChromaDB index 構築")
    parser.add_argument("--force", action="store_true",
                        help="既存 collection を削除して再構築")
    args = parser.parse_args()

    result = build_index(force=args.force)
    print(f"\n=== 結果 ===")
    for k, v in result.items():
        print(f"  {k:>20}: {v}")
