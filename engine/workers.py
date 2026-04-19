"""백그라운드 워커 — 저장 후 AI/외부 출처의 카테고리·별칭 수집 (v15-A2).
① 카테고리 분류: base 모델 + CATEGORY_SYSTEMPROMPT.md → origin='ai'
② Wikidata 별칭: altLabel(ko·en) → origin='external'
register_post_save_hook 디스패처가 SaveResult.node_ids_added 를 수신.
실패·빈 결과는 무음 스킵(자연 재시도). llm_fn/wikidata_fn 주입으로 단위 테스트.
설계: docs/DESIGN_PIPELINE.md "백그라운드 워커".
"""

from __future__ import annotations
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from typing import Callable, Optional

from .db import DB_PATH, get_connection
from .save import SaveResult, register_post_save_hook

CategoryLLMFn = Callable[[str, list[str]], list[str]]
WikidataAliasFn = Callable[[str], list[str]]

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_CATEGORY_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "CATEGORY_SYSTEMPROMPT.md")


def _node_name(db_path: str, node_id: int) -> Optional[str]:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT name FROM nodes WHERE id=?", (node_id,)).fetchone()
    finally:
        conn.close()
    return row["name"] if row else None


def _recent_sentences(db_path: str, node_id: int, limit: int = 5) -> list[str]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT s.text FROM node_mentions m JOIN sentences s ON s.id=m.sentence_id
               WHERE m.node_id=? ORDER BY s.created_at DESC LIMIT ?""",
            (node_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [r["text"] for r in rows]


# ─── 워커 ① 카테고리 분류 ─────────────────────────────────

def _default_category_llm(node_name: str, sentences: list[str]) -> list[str]:
    """베이스 모델 + CATEGORY_SYSTEMPROMPT.md 로 분류."""
    from .llm import chat
    try:
        with open(_CATEGORY_PROMPT_PATH, encoding="utf-8") as f:
            system = f.read()
    except FileNotFoundError:
        return []
    user = f"노드: {node_name}\n최근 문장:\n" + "\n".join(f"- {s}" for s in sentences)
    try:
        raw = chat(system, user, temperature=0, max_tokens=256)
    except Exception:
        return []
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return []
    return [c for c in data.get("categories", []) if isinstance(c, str) and c]


def category_worker(
    node_ids: list[int], db_path: str = DB_PATH,
    llm_fn: Optional[CategoryLLMFn] = None,
) -> int:
    """신규 노드 목록에 AI 카테고리 분류 + origin='ai' INSERT. 반환: INSERT 건수."""
    if not node_ids:
        return 0
    llm_fn = llm_fn or _default_category_llm
    inserted = 0
    for node_id in node_ids:
        name = _node_name(db_path, node_id)
        if not name:
            continue
        try:
            categories = llm_fn(name, _recent_sentences(db_path, node_id))
        except Exception as e:
            print(f"[workers/category] node_id={node_id} 실패: {e}")
            continue
        if not categories:
            continue
        conn = get_connection(db_path)
        try:
            for cat in categories:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO node_categories "
                    "(node_id, category, origin) VALUES (?,?,?)",
                    (node_id, cat, "ai"),
                )
                inserted += cur.rowcount
            conn.commit()
        finally:
            conn.close()
    return inserted


# ─── 워커 ② Wikidata 별칭 ─────────────────────────────────

def _default_wikidata_alias(node_name: str) -> list[str]:
    """wbsearchentities → wbgetentities(aliases, ko|en). 실패·빈 결과는 []."""
    try:
        q1 = urllib.parse.urlencode({
            "action": "wbsearchentities", "search": node_name,
            "language": "ko", "format": "json", "limit": 1,
        })
        with urllib.request.urlopen(f"{WIKIDATA_API}?{q1}", timeout=10) as r:
            hits = json.loads(r.read().decode()).get("search", [])
        if not hits:
            return []
        qid = hits[0]["id"]
        q2 = urllib.parse.urlencode({
            "action": "wbgetentities", "ids": qid, "props": "aliases",
            "languages": "ko|en", "format": "json",
        })
        with urllib.request.urlopen(f"{WIKIDATA_API}?{q2}", timeout=10) as r:
            data = json.loads(r.read().decode())
        aliases_data = data.get("entities", {}).get(qid, {}).get("aliases", {})
    except Exception:
        return []
    out: list[str] = []
    for lang in ("ko", "en"):
        for a in aliases_data.get(lang, []):
            val = (a.get("value") or "").strip()
            if val and val != node_name:
                out.append(val)
    return out


def alias_worker(
    node_ids: list[int], db_path: str = DB_PATH,
    wikidata_fn: Optional[WikidataAliasFn] = None,
) -> int:
    """신규 노드 목록에 Wikidata altLabel + origin='external' INSERT. 반환: INSERT 건수."""
    if not node_ids:
        return 0
    wikidata_fn = wikidata_fn or _default_wikidata_alias
    inserted = 0
    for node_id in node_ids:
        name = _node_name(db_path, node_id)
        if not name:
            continue
        try:
            aliases = wikidata_fn(name)
        except Exception as e:
            print(f"[workers/alias] node_id={node_id} 실패: {e}")
            continue
        if not aliases:
            continue
        conn = get_connection(db_path)
        try:
            for alias in aliases:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO aliases "
                    "(alias, node_id, origin) VALUES (?,?,?)",
                    (alias, node_id, "external"),
                )
                inserted += cur.rowcount
            conn.commit()
        finally:
            conn.close()
    return inserted


# ─── save 훅 어댑터 ────────────────────────────────────────
def run_workers(result: SaveResult, db_path: str) -> None:
    """두 워커를 순차 실행. 예외는 격리."""
    node_ids = list(result.node_ids_added)
    if not node_ids:
        return
    for name, fn in (("category", category_worker), ("alias", alias_worker)):
        try:
            fn(node_ids, db_path)
        except Exception as e:
            print(f"[workers] {name}_worker 예외: {e}")


def install_default_hooks(background: bool = True) -> None:
    """save() 훅에 워커 디스패처 등록. background=True 면 daemon 스레드로 실행."""
    def hook(result: SaveResult, db_path: str) -> None:
        if background:
            threading.Thread(
                target=run_workers, args=(result, db_path), daemon=True
            ).start()
        else:
            run_workers(result, db_path)
    register_post_save_hook(hook)
