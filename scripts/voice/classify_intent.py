"""Gemma 4 によるインテント分類モジュール.

Ollama HTTP API（OpenAI互換エンドポイント）経由でローカルLLMを呼び出し、
来場者発話を7インテントに分類する。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError as e:
    raise ImportError(
        "requests ライブラリが見つかりません。pip install requests を実行してください。"
    ) from e


OLLAMA_URL: str = "http://localhost:11434/v1/chat/completions"
MODEL: str = "gemma4:e4b"

# スクリプト位置: <project_root>/scripts/voice/classify_intent.py
# プロンプト位置: <project_root>/data/prompts/intent_classification_v1.md
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
PROMPT_PATH: Path = _PROJECT_ROOT / "data" / "prompts" / "intent_classification_v1.md"


_FALLBACK_PROMPT: str = """# シーマ事例検索 インテント分類プロンプト v1 (フォールバック)

あなたはシーマ社の事例検索サイネージのAIナビゲーターです。
来場者の発話を以下の7つのインテントに分類し、JSON形式で返してください。

## インテント定義

1. DIRECT_RECALL：固有名指定（施主名・施設名で直接呼び出し）
2. FILTER_SEARCH：用途絞り込み（用途×設備の組合せ）
3. SPEC_SEARCH：仕様絞り込み（ピッチ・屋内外などの技術指定）
4. CONSULTATION：抽象的な相談
5. TERM_EXPLAIN：専門用語の説明要求
6. COMPARISON：複数事例・仕様の比較
7. NAVIGATION：画面操作（次・前・戻る等）

## 出力フォーマット

JSONのみを返してください。コードブロック記号、前置き、説明文は一切不要です。

{"intent": "DIRECT_RECALL", "extracted_entities": {"client_name": "ガーナーホテル"}, "confidence": 0.95}

## ルール

- JSONのみ返す
- 前置きや説明文を一切付けない
- 該当エンティティがなければ extracted_entities は {} とする
- confidence は 0.0〜1.0 の数値
"""


def load_system_prompt() -> str:
    """システムプロンプトを data/prompts/intent_classification_v1.md から読み込む.

    ファイルが存在しない場合、仮プロンプトを同パスに新規作成して返す。

    Returns:
        プロンプト文字列。
    """
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")

    print(f"[classify] プロンプトが見つかりません。仮プロンプトを作成: {PROMPT_PATH}")
    PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMPT_PATH.write_text(_FALLBACK_PROMPT, encoding="utf-8")
    return _FALLBACK_PROMPT


def _extract_json_block(text: str) -> dict[str, Any]:
    """LLM応答からJSONブロックを抽出してdictへパースする.

    最初の "{" と最後の "}" の間をJSONとみなしてパースする
    （前置き・コードブロック記号への耐性）。

    Args:
        text: LLM生応答テキスト。

    Returns:
        パース結果の辞書。

    Raises:
        ValueError: JSONブロックが見つからない、または不正なJSON。
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"応答中にJSONブロックが見つかりません: {text[:200]}")
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSONパース失敗: {e} / snippet={snippet[:200]}") from e


def classify_intent(text: str, system_prompt: str) -> dict[str, Any]:
    """発話テキストをインテント分類する.

    Ollama に gemma4:e4b でリクエストし、JSON出力をパースして返す。
    失敗時は error キーを含むdictを返す（例外を投げない）。

    Args:
        text: 文字起こし済み発話テキスト。
        system_prompt: システムプロンプト文字列（load_system_prompt() の結果）。

    Returns:
        成功時:
            {"intent": str, "extracted_entities": dict, "confidence": float,
             "duration_sec": float}
        失敗時:
            {"error": str, "duration_sec": float, "raw_response": str (任意)}
    """
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
        "max_tokens": 200,
        "stream": False,
    }

    start = time.time()

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=30)
    except requests.exceptions.ConnectionError as e:
        return {
            "error": (
                "Ollama に接続できません。`ollama serve` でサービスを起動してください。"
                f" 詳細: {e}"
            ),
            "duration_sec": time.time() - start,
        }
    except requests.exceptions.Timeout:
        return {
            "error": "Ollama 応答タイムアウト（30秒超過）",
            "duration_sec": time.time() - start,
        }

    elapsed = time.time() - start

    if resp.status_code != 200:
        return {
            "error": f"Ollama HTTPエラー: status={resp.status_code}, body={resp.text[:200]}",
            "duration_sec": elapsed,
        }

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, ValueError) as e:
        return {
            "error": f"Ollama応答パース失敗: {e}",
            "raw_response": resp.text[:500],
            "duration_sec": elapsed,
        }

    try:
        parsed = _extract_json_block(content)
    except ValueError as e:
        return {
            "error": str(e),
            "raw_response": content,
            "duration_sec": elapsed,
        }

    parsed.setdefault("extracted_entities", {})
    parsed["duration_sec"] = elapsed
    return parsed


if __name__ == "__main__":
    # 単体動作確認用
    import sys

    if len(sys.argv) < 2:
        print('使い方: python classify_intent.py "<text>"')
        sys.exit(1)

    sp = load_system_prompt()
    r = classify_intent(sys.argv[1], sp)
    print(json.dumps(r, ensure_ascii=False, indent=2))
