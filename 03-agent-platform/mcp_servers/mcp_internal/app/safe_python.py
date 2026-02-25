import hashlib
from typing import Any, Dict

from app.sqlite_store import run_safe_query


def task_math_add(args: Dict[str, Any]) -> Dict[str, Any]:
    a = float(args.get("a"))
    b = float(args.get("b"))
    return {"a": a, "b": b, "sum": a + b}


def task_text_word_count(args: Dict[str, Any]) -> Dict[str, Any]:
    text = str(args.get("text", ""))
    # simple tokenizer (whitespace)
    words = [w for w in text.strip().split() if w]
    return {"words": len(words), "chars": len(text)}


def task_util_sha256(args: Dict[str, Any]) -> Dict[str, Any]:
    text = str(args.get("text", ""))
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"sha256": h}


def task_data_sum_orders_by_user(args: Dict[str, Any]) -> Dict[str, Any]:
    # Reuse a whitelist query in sqlite_store
    sqlite_path = args.get("sqlite_path")
    if sqlite_path:
        rows = run_safe_query("sum_orders_by_user", {}, sqlite_path=str(sqlite_path))
    else:
        rows = run_safe_query("sum_orders_by_user", {}, sqlite_path=None)  # type: ignore
    return {"rows": rows}


SAFE_TASKS = {
    "math.add": task_math_add,
    "text.word_count": task_text_word_count,
    "util.sha256": task_util_sha256,
    "data.sum_orders_by_user": task_data_sum_orders_by_user,
}


def run_task(task: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if task not in SAFE_TASKS:
        raise ValueError("task_not_allowed")
    return SAFE_TASKS[task](args)
