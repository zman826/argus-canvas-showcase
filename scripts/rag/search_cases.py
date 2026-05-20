"""インテント別 事例検索ディスパッチ.

intent + extracted_entities + クエリ全文を受け取り、最適な検索戦略を選んで
top-K の事例を返す。

戦略マッピング:
    DIRECT_RECALL  : entity (client_name 等) を fuzzy_match.fuzzy_match_against_titles
                     ヒットなければ semantic にフォールバック
    FILTER_SEARCH  : entity (client_type, product_type) を facility/tag フラグに変換し
                     ChromaDB where 絞り込み + semantic
    SPEC_SEARCH    : entity (pitch_mm, indoor_outdoor) を spec フラグに変換し
                     ChromaDB where 絞り込み + semantic
    CONSULTATION   : pure semantic search（top-K）
    TERM_EXPLAIN   : pure semantic search（term を含むクエリで）
    COMPARISON     : pure semantic search（target_a / target_b を含むクエリで）
    NAVIGATION     : RAG 不要、空リスト返却
"""
from __future__ import annotations

import time
from typing import Any

from build_index import encode_query, get_collection
from fuzzy_match import fuzzy_match_against_titles
from load_data import load_cases

# Gemma が分類で出す entity 値 → ChromaDB metadata フラグへのマッピング
CLIENT_TYPE_TO_FACILITY_FLAG: dict[str, str] = {
    "hotel": "facility_hotel",
    "school": "facility_school",
    "commercial": "facility_store",        # 商業施設 ≒ store
    "museum": "facility_museum",
    "station": "facility_station",
    "expo": "facility_expo",
    "showroom": "facility_showroom",
    "exhibition": "facility_exhibition",
    "hall": "facility_hall",
    "event": "facility_event",
}

PRODUCT_TYPE_TO_TAG_FLAG: dict[str, str] = {
    "led_vision": "tag_led_vision",
    "led": "tag_led_vision",
    "projection_mapping": "tag_projection_mapping",
    "projection": "tag_projection_mapping",
    "kairos": "tag_kairos",
}


def _format_chroma_hit(idx: int, results: dict[str, Any], match_type: str) -> dict[str, Any]:
    """ChromaDB query 結果から1件分を整形する.

    Args:
        idx: results 内のインデックス。
        results: collection.query() の戻り値（{"ids": [[...]], "distances": [[...]], "metadatas": [[...]]}）。
        match_type: "fuzzy"|"filter_semantic"|"semantic" 等の識別子。

    Returns:
        {"id", "title", "score", "match_type", "metadata"} の dict。
    """
    md = results["metadatas"][0][idx]
    dist = results["distances"][0][idx] if "distances" in results else None
    # cosine distance → similarity に変換（0 が完全一致、2 が逆向き）
    similarity = 1.0 - dist if dist is not None else None
    return {
        "id": int(md["id"]),
        "title": md.get("title", ""),
        "score": round(similarity, 4) if similarity is not None else None,
        "distance": round(dist, 4) if dist is not None else None,
        "match_type": match_type,
        "metadata": {
            k: v for k, v in md.items()
            if k in ("year", "primary_facility_type", "tags_csv", "facility_types_csv")
        },
    }


def _format_fuzzy_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """fuzzy_match_against_titles の結果を統一形式に変換."""
    return {
        "id": hit["id"],
        "title": hit["title"],
        "score": None,
        "distance": hit["distance"],
        "match_type": f"fuzzy_{hit['match_type']}",
        "metadata": {},
    }


def _semantic_with_filter(
    query: str,
    where: dict[str, Any] | None,
    top_k: int,
    match_type: str,
) -> list[dict[str, Any]]:
    """ChromaDB query 実行のヘルパ."""
    collection = get_collection()
    query_emb = encode_query(query)
    kwargs: dict[str, Any] = {
        "query_embeddings": [query_emb],
        "n_results": top_k,
    }
    if where:
        kwargs["where"] = where
    results = collection.query(**kwargs)
    if not results.get("ids") or not results["ids"][0]:
        return []
    return [_format_chroma_hit(i, results, match_type) for i in range(len(results["ids"][0]))]


def _search_direct_recall(
    entities: dict[str, Any],
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """DIRECT_RECALL: 固有名 fuzzy 優先、外れたら semantic."""
    # entity に何が入っていても拾う
    name = (
        entities.get("client_name")
        or entities.get("term")
        or entities.get("title")
        or query
    )
    cases = load_cases()
    fuzzy_hits = fuzzy_match_against_titles(name, cases, top_k=top_k)
    if fuzzy_hits:
        return [_format_fuzzy_hit(h) for h in fuzzy_hits]
    return _semantic_with_filter(query, None, top_k, "semantic_fallback")


def _build_filter_where(entities: dict[str, Any]) -> dict[str, Any]:
    """FILTER_SEARCH の entities から ChromaDB where 句を組み立てる."""
    conditions: list[dict[str, Any]] = []

    ct = entities.get("client_type")
    if isinstance(ct, str):
        flag = CLIENT_TYPE_TO_FACILITY_FLAG.get(ct.lower())
        if flag:
            conditions.append({flag: True})

    pt = entities.get("product_type")
    if isinstance(pt, str):
        flag = PRODUCT_TYPE_TO_TAG_FLAG.get(pt.lower())
        if flag:
            conditions.append({flag: True})

    if len(conditions) == 0:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _search_filter(
    entities: dict[str, Any],
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """FILTER_SEARCH: facility/tag フラグで絞り込み + semantic."""
    where = _build_filter_where(entities)
    if where:
        hits = _semantic_with_filter(query, where, top_k, "filter_semantic")
        if hits:
            return hits
    # フィルタ無し or 0件 → 全件 semantic
    return _semantic_with_filter(query, None, top_k, "semantic_fallback")


def _search_spec(
    entities: dict[str, Any],
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """SPEC_SEARCH: ピッチ・屋内屋外で絞り込み.

    実データには spec 用語がほぼ含まれないため、ほとんどのケースで filter は
    効かず semantic フォールバックになる見込み。
    """
    conditions: list[dict[str, Any]] = []
    if "pitch_mm" in entities or "pitch" in entities:
        conditions.append({"has_pitch": True})
    io = entities.get("indoor_outdoor")
    if isinstance(io, str) and io in ("indoor", "outdoor", "both"):
        conditions.append({"indoor_outdoor": io})

    where = (
        {} if not conditions
        else conditions[0] if len(conditions) == 1
        else {"$and": conditions}
    )

    if where:
        hits = _semantic_with_filter(query, where, top_k, "filter_semantic")
        if hits:
            return hits
    return _semantic_with_filter(query, None, top_k, "semantic_fallback")


def _search_semantic_only(query: str, top_k: int) -> list[dict[str, Any]]:
    """CONSULTATION / TERM_EXPLAIN / COMPARISON: 純粋ベクトル検索."""
    return _semantic_with_filter(query, None, top_k, "semantic")


def search(
    intent: str | None,
    entities: dict[str, Any] | None,
    query: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """インテント別検索ディスパッチのエントリポイント.

    Args:
        intent: classify_intent.py の出力。None なら semantic にフォールバック。
        entities: classify_intent.py の extracted_entities。
        query: ASR 後・正規化済みの発話テキスト（embedding 用）。
        top_k: 返す最大件数。

    Returns:
        {
            "intent": str,
            "matched_cases": list[dict],   # 各要素は _format_chroma_hit() の形式
            "rag_time_sec": float,
        }
    """
    entities = entities or {}
    t0 = time.time()

    if intent == "NAVIGATION":
        return {"intent": intent, "matched_cases": [], "rag_time_sec": 0.0}

    try:
        if intent == "DIRECT_RECALL":
            hits = _search_direct_recall(entities, query, top_k)
        elif intent == "FILTER_SEARCH":
            hits = _search_filter(entities, query, top_k)
        elif intent == "SPEC_SEARCH":
            hits = _search_spec(entities, query, top_k)
        elif intent in ("CONSULTATION", "TERM_EXPLAIN", "COMPARISON"):
            hits = _search_semantic_only(query, top_k)
        else:
            # 未知 intent → semantic フォールバック
            hits = _search_semantic_only(query, top_k)
    except Exception as e:  # noqa: BLE001 - DB エラー等を一括捕捉
        return {
            "intent": intent,
            "matched_cases": [],
            "rag_time_sec": round(time.time() - t0, 3),
            "error": str(e),
        }

    return {
        "intent": intent,
        "matched_cases": hits,
        "rag_time_sec": round(time.time() - t0, 3),
    }


if __name__ == "__main__":
    # 単体動作テスト：仕様書記載の10ケースを検証
    test_cases: list[tuple[str, str, dict[str, Any], int | str]] = [
        ("DIRECT_RECALL", "ガーナーホテルの事例を見せて",
         {"client_name": "ガーナーホテル"}, 113),
        ("DIRECT_RECALL", "ガーナホテルの事例（誤認識想定）",
         {"client_name": "ガーナホテル"}, 113),
        ("FILTER_SEARCH", "ホテルの事例",
         {"client_type": "hotel"}, "facility=hotel"),
        ("FILTER_SEARCH", "大阪・関西万博の事例",
         {"client_type": "expo"}, "tag=大阪・関西万博 (8件)"),
        ("FILTER_SEARCH", "LEDビジョンの事例",
         {"product_type": "led_vision"}, "tag=LEDビジョン (30件)"),
        ("DIRECT_RECALL", "新宿駅の事例", {"client_name": "新宿駅"}, 105),
        ("DIRECT_RECALL", "コマツの事例", {"client_name": "コマツ"}, 1),
        ("FILTER_SEARCH", "KAIROSの事例", {"product_type": "kairos"}, "tag=KAIROS (13件)"),
        ("FILTER_SEARCH", "プロジェクションマッピングの事例",
         {"product_type": "projection_mapping"}, "tag=プロジェクションマッピング (34件)"),
        ("DIRECT_RECALL", "セネガルパビリオン",
         {"client_name": "セネガルパビリオン"}, 107),
    ]

    print("=" * 70)
    print("検索動作テスト（10ケース）")
    print("=" * 70)

    for intent, query, entities, expected in test_cases:
        print(f"\n[{intent}] 「{query}」")
        print(f"  entities: {entities}")
        print(f"  expected: {expected}")
        result = search(intent, entities, query, top_k=5)
        print(f"  rag_time_sec: {result['rag_time_sec']}")
        print(f"  matched_cases ({len(result['matched_cases'])}):")
        for i, hit in enumerate(result["matched_cases"][:5]):
            print(f"    {i+1}. id={hit['id']:>3}  type={hit['match_type']:<20}  "
                  f"score={hit['score']}  title={hit['title'][:40]}")
