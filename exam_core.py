"""Pure comparison and portable-attempt logic; no execution of student code."""
from __future__ import annotations

import copy
import csv
import io
import json
import math
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

SCHEMA = 1
MAX_BACKUP_BYTES = 4_000_000


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_attempt(exam, questions, mode="Practice"):
    return {
        "schema": SCHEMA, "id": str(uuid.uuid4()), "title": exam["title"],
        "exam_id": exam["id"], "content_version": "2026.10.20.2",
        "created_at": now(), "updated_at": now(), "status": "in_progress",
        "mode": mode, "duration": 300 if all(q["subject"] == "Interpretation" for q in questions) else 480,
        "elapsed": 0.0, "running_since": None, "position": 0,
        "questions": copy.deepcopy(questions),
        "responses": {}, "notes": "", "revision": 0,
    }


def elapsed(attempt, at=None):
    current = time.time() if at is None else at
    return attempt["elapsed"] + (
        max(0, current - attempt["running_since"])
        if attempt.get("running_since") is not None else 0
    )


def pause(attempt, at=None):
    attempt["elapsed"] = elapsed(attempt, at)
    attempt["running_since"] = None


def touch(attempt):
    attempt["updated_at"] = now()
    attempt["revision"] += 1


def portable(attempt):
    snapshot = copy.deepcopy(attempt)
    pause(snapshot)
    return snapshot


def export_attempt(attempt):
    return json.dumps(portable(attempt), ensure_ascii=False, indent=2, allow_nan=False)


def validate_attempt(raw):
    """Strictly validate imports before they can become app state.

    Embedded question snapshots are treated as data, never SQL, Python or HTML.
    """
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise ValueError("This is not a supported Exam Studio backup.")
    try:
        uuid.UUID(raw["id"])
        for key in ("title", "exam_id", "content_version", "created_at", "updated_at", "notes"):
            if not isinstance(raw[key], str) or len(raw[key]) > 20000:
                raise ValueError("Invalid text field.")
        for key in ("created_at", "updated_at"):
            datetime.fromisoformat(raw[key])
        if raw["status"] not in ("in_progress", "completed"):
            raise ValueError("Invalid attempt status.")
        if raw["mode"] not in ("Practice", "Exam"):
            raise ValueError("Invalid practice mode.")
        for key in ("elapsed", "duration"):
            value = raw[key]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 10000000:
                raise ValueError("Invalid timer.")
        qs = raw["questions"]
        if not isinstance(qs, list) or not 1 <= len(qs) <= 40:
            raise ValueError("Invalid question list.")
        ids = set()
        for q in qs:
            for key in ("id", "title", "prompt", "subject", "skill", "source", "hint", "solution"):
                if not isinstance(q[key], str) or len(q[key]) > 20000:
                    raise ValueError("Invalid question.")
            if q["id"] in ids:
                raise ValueError("Duplicate question.")
            ids.add(q["id"])
            if q["kind"] not in ("number", "table", "explain"):
                raise ValueError("Unknown answer type.")
            if not isinstance(q["datasets"], list) or any(not isinstance(x, str) for x in q["datasets"]):
                raise ValueError("Invalid dataset list.")
            if q["kind"] == "number":
                if not isinstance(q["answer"], (float, int)) or not math.isfinite(q["answer"]):
                    raise ValueError("Invalid reference value.")
                if not isinstance(q.get("tolerance", 0.01), (int, float)) or not 0 <= q.get("tolerance", 0.01) <= 100:
                    raise ValueError("Invalid tolerance.")
            if q["kind"] == "table":
                cols, rows = q["columns"], q["answer"]
                if not isinstance(cols, list) or not 1 <= len(cols) <= 30 or any(not isinstance(c, str) for c in cols):
                    raise ValueError("Invalid result columns.")
                if not isinstance(rows, list) or len(rows) > 2000:
                    raise ValueError("Invalid result rows.")
                for row in rows:
                    if not isinstance(row, list) or len(row) != len(cols):
                        raise ValueError("Invalid result shape.")
                    if any(v is not None and not isinstance(v, (str, float, int)) for v in row):
                        raise ValueError("Invalid result cell.")
            if q["kind"] == "explain" and (not isinstance(q["rubric"], list) or any(not isinstance(x, str) for x in q["rubric"])):
                raise ValueError("Invalid self-review rubric.")
        if type(raw["position"]) is not int or not 0 <= raw["position"] < len(qs):
            raise ValueError("Invalid active question.")
        if type(raw["revision"]) is not int or raw["revision"] < 0:
            raise ValueError("Invalid revision.")
        if not isinstance(raw["responses"], dict) or not set(raw["responses"]).issubset(ids):
            raise ValueError("Invalid responses.")
        for response in raw["responses"].values():
            for key in ("answer", "method"):
                if not isinstance(response[key], str) or len(response[key]) > 20000:
                    raise ValueError("Invalid response text.")
            if not isinstance(response["history"], list) or len(response["history"]) > 300:
                raise ValueError("Invalid feedback history.")
            for record in response["history"]:
                for key in ("at", "answer", "method", "status", "message"):
                    if not isinstance(record[key], str) or len(record[key]) > 20000:
                        raise ValueError("Invalid feedback entry.")
                if record["status"] not in ("match", "retry", "review"):
                    raise ValueError("Invalid feedback status.")
            history = response.get("ai_history", [])
            if not isinstance(history, list) or len(history) > 100:
                raise ValueError("Invalid AI conversation.")
            for turn in history:
                if not isinstance(turn, dict):
                    raise ValueError("Invalid AI message.")
                if turn.get("role") not in ("user", "assistant"):
                    raise ValueError("Invalid AI message role.")
                for key in ("content", "at"):
                    if not isinstance(turn.get(key), str) or len(turn[key]) > 20000:
                        raise ValueError("Invalid AI message.")
            draft = response.get("ai_draft", {})
            if not isinstance(draft, dict) or any(not isinstance(v, str) or len(v) > 20000 for v in draft.values()):
                raise ValueError("Invalid AI draft.")
            if type(response.get("ai_context_start", 0)) is not int or not 0 <= response.get("ai_context_start", 0) <= len(history):
                raise ValueError("Invalid AI conversation boundary.")
        result = copy.deepcopy(raw)
        result["duration"] = 300 if all(q["subject"] == "Interpretation" for q in qs) else 480
        # A restored attempt is paused; time away is not practice time.
        result["running_since"] = None
        return result
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("The backup is incomplete or malformed.") from exc


def import_attempt(content):
    if len(content) > MAX_BACKUP_BYTES:
        raise ValueError("This backup is too large (maximum 4 MB).")
    try:
        raw = json.loads(content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Please choose a valid Exam Studio JSON backup.") from exc
    return validate_attempt(raw)


def number(text):
    text = str(text).strip().replace("\u00a0", "").replace(" ", "")
    # Unambiguous grouping only. A decimal comma is accepted when no dot occurs.
    if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", text):
        text = text.replace(",", "")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        value = Decimal(text)
        if not value.is_finite():
            raise ValueError("Enter a finite number.")
        return value
    except InvalidOperation as exc:
        raise ValueError("Enter a number without units or a percent sign.") from exc


def cell_equal(actual, expected, tolerance):
    if expected is None:
        return actual.strip().casefold() in ("", "null")
    if isinstance(expected, (int, float)):
        try:
            return abs(number(actual) - Decimal(str(expected))) <= Decimal(str(tolerance))
        except ValueError:
            return False
    return actual.strip() == str(expected).strip()


def parse_table(text):
    lines = text.strip().splitlines()
    if not lines:
        raise ValueError("Paste your result table, including column headers.")
    delimiter = "\t" if "\t" in lines[0] else ";" if ";" in lines[0] else ","
    rows = list(csv.reader(io.StringIO(text.strip()), delimiter=delimiter))
    if len(rows) < 2:
        raise ValueError("Include the header and at least one data row.")
    if len(rows) > 2001:
        raise ValueError("Paste a result table with no more than 2,000 rows.")
    if any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("The rows have different widths. Copy a rectangular table from Excel, or use quoted CSV.")
    return [h.strip().casefold() for h in rows[0]], rows[1:]


def check(question, answer):
    kind = question["kind"]
    if not answer.strip():
        return {"status": "retry", "message": "Enter your result before checking."}
    if kind == "explain":
        return {"status": "review", "message": "Explanation saved. Review your reasoning against the checklist below; this is not an automatic grade."}
    tolerance = question.get("tolerance", 0.01)
    if kind == "number":
        try:
            value = number(answer)
        except ValueError as exc:
            return {"status": "retry", "message": str(exc)}
        if abs(value - Decimal(str(question["answer"]))) <= Decimal(str(tolerance)):
            return {"status": "match", "message": "Output matches the reference. Be ready to explain your method."}
        for diagnostic in question.get("diagnostics", []):
            if abs(value - Decimal(str(diagnostic["value"]))) <= Decimal(str(tolerance)):
                return {"status": "retry", "message": diagnostic["message"]}
        return {"status": "retry", "message": "This value does not match yet. " + question["hint"]}
    try:
        headers, rows = parse_table(answer)
    except ValueError as exc:
        return {"status": "retry", "message": str(exc)}
    wanted = [c.casefold() for c in question["columns"]]
    if headers != wanted:
        return {"status": "retry", "message": "Use these column headers, in this order: " + ", ".join(question["columns"]) + "."}
    reference = question["answer"]
    if len(rows) != len(reference):
        return {"status": "retry", "message": f"Your table has {len(rows)} rows; this task expects {len(reference)}. Check filters, grouping and duplicate matches."}

    def same(a, b):
        return all(cell_equal(x, y, tolerance) for x, y in zip(a, b))

    if question.get("ordered", False):
        good = all(same(a, b) for a, b in zip(rows, reference))
    else:
        # Multiset comparison: duplicate rows are meaningful, never silently dropped.
        remaining = list(reference)
        good = True
        for row in rows:
            index = next((i for i, candidate in enumerate(remaining) if same(row, candidate)), None)
            if index is None:
                good = False
                break
            remaining.pop(index)
    if good:
        return {"status": "match", "message": "Output matches the reference, including its rows and values. This checks the result, not the method."}
    return {"status": "retry", "message": "The shape is right, but some values" + (" or their order" if question.get("ordered") else "") + " differ. " + question["hint"]}


def submit(attempt, question, answer, method):
    result = check(question, answer)
    response = attempt["responses"].setdefault(question["id"], {"answer": "", "method": "", "history": []})
    response.update(answer=answer, method=method)
    response["history"].append({"at": now(), "answer": answer, "method": method, **result})
    response["history"] = response["history"][-300:]
    touch(attempt)
    return result
