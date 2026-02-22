"""LLM response parsing — ported from shared.ts parsePlannerResponse / parseLLMTaskArray."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from .types import FileOperation, Handoff, HandoffMetrics, WorkerResult

logger = logging.getLogger("agentswarm.parsing")


@dataclass
class RawTaskInput:
    id: str | None = None
    description: str = ""
    scope: list[str] | None = None
    acceptance: str | None = None
    priority: int | None = None
    team: str | None = None


@dataclass
class PlannerResponse:
    scratchpad: str
    tasks: list[RawTaskInput]


# ---------------------------------------------------------------------------
# JSON repair utilities
# ---------------------------------------------------------------------------

def _try_json_loads(text: str) -> dict | list | None:
    """Try json.loads, return None on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _repair_json(text: str) -> str:
    """Attempt to repair common JSON issues from LLM output.

    The #1 problem: LLMs put literal newlines inside JSON string values
    (the "content" field with source code). Standard JSON requires \\n instead.

    Strategy: Walk through the JSON character by character. When inside a string,
    replace literal newlines with \\n, literal tabs with \\t.
    """
    # Fast path: already valid.
    if _try_json_loads(text) is not None:
        return text

    # Fix literal newlines/tabs inside JSON strings.
    repaired = _fix_literal_newlines_in_strings(text)
    if _try_json_loads(repaired) is not None:
        return repaired

    # Try removing trailing commas before ] or }.
    repaired2 = re.sub(r',\s*([}\]])', r'\1', repaired)
    if _try_json_loads(repaired2) is not None:
        return repaired2

    # Try truncation repair — close open braces/brackets.
    repaired3 = _fix_truncated_json(repaired2)
    if repaired3 and _try_json_loads(repaired3) is not None:
        return repaired3

    # Return best attempt even if still broken.
    return repaired


def _fix_literal_newlines_in_strings(text: str) -> str:
    """Replace literal newlines/tabs inside JSON string values with escape sequences.

    Walks the JSON character by character, tracking whether we're inside a string.
    Inside strings: literal \\n -> \\\\n, literal \\r -> \\\\r, literal \\t -> \\\\t.
    """
    output = []
    i = 0
    in_string = False

    while i < len(text):
        ch = text[i]

        if not in_string:
            if ch == '"':
                in_string = True
            output.append(ch)
        else:
            # Inside a JSON string.
            if ch == '\\':
                # Escaped character — keep the escape pair as-is.
                if i + 1 < len(text):
                    output.append(ch)
                    output.append(text[i + 1])
                    i += 2
                    continue
                else:
                    output.append(ch)
            elif ch == '"':
                in_string = False
                output.append(ch)
            elif ch == '\n':
                output.append('\\n')
            elif ch == '\r':
                output.append('\\r')
            elif ch == '\t':
                output.append('\\t')
            else:
                output.append(ch)

        i += 1

    return "".join(output)


def _fix_truncated_json(text: str) -> str | None:
    """Try to close a truncated JSON object by adding missing brackets/braces."""
    open_braces = 0
    open_brackets = 0
    in_string = False
    i = 0

    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == '\\' and i + 1 < len(text):
                i += 2
                continue
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == '{':
                open_braces += 1
            elif ch == '}':
                open_braces -= 1
            elif ch == '[':
                open_brackets += 1
            elif ch == ']':
                open_brackets -= 1
        i += 1

    if open_braces <= 0 and open_brackets <= 0:
        return None

    suffix = ""
    if in_string:
        suffix += '"'
    suffix += ']' * max(0, open_brackets)
    suffix += '}' * max(0, open_braces)

    return text.rstrip() + suffix


# ---------------------------------------------------------------------------
# Planner response parsing
# ---------------------------------------------------------------------------


def _strip_markdown_fences(text: str) -> str:
    """Remove outermost markdown code fences if present."""
    result = text
    for _ in range(3):
        m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", result)
        if m:
            inner = m.group(1).strip()
            if inner and (inner[0] in '{[' or '"' in inner[:20]):
                result = inner
            else:
                break
        else:
            break
    return result


def _salvage_truncated_response(content: str) -> PlannerResponse:
    """Character-by-character extraction of complete JSON objects from a
    potentially truncated LLM response."""
    scratchpad = ""
    tasks: list[RawTaskInput] = []

    # Try to extract the scratchpad string.
    sp_match = re.search(r'"scratchpad"\s*:\s*"((?:[^"\\]|\\.)*)"', content)
    if sp_match:
        try:
            scratchpad = json.loads(f'"{sp_match.group(1)}"')
        except Exception:
            scratchpad = sp_match.group(1)

    # Locate "tasks": [ and walk character-by-character to extract each {...}.
    tk_match = re.search(r'"tasks"\s*:\s*\[', content)
    if not tk_match:
        return PlannerResponse(scratchpad=scratchpad, tasks=tasks)

    remainder = content[tk_match.end():]
    depth = 0
    obj_start = -1
    i = 0

    while i < len(remainder):
        ch = remainder[i]

        # Skip over JSON string literals to avoid counting braces inside them.
        if ch == '"':
            i += 1
            while i < len(remainder):
                if remainder[i] == '\\':
                    i += 1  # skip escaped char
                elif remainder[i] == '"':
                    break
                i += 1
            i += 1
            continue

        if ch == '{':
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and obj_start != -1:
                obj_str = remainder[obj_start:i + 1]
                # Try direct parse, then repair.
                raw = _try_json_loads(obj_str)
                if raw is None:
                    repaired = _repair_json(obj_str)
                    raw = _try_json_loads(repaired)
                if isinstance(raw, dict) and raw.get("description"):
                    tasks.append(_dict_to_raw(raw))
                obj_start = -1

        i += 1

    return PlannerResponse(scratchpad=scratchpad, tasks=tasks)


def _dict_to_raw(d: dict) -> RawTaskInput:
    return RawTaskInput(
        id=d.get("id"),
        description=d.get("description", ""),
        scope=d.get("scope"),
        acceptance=d.get("acceptance"),
        priority=d.get("priority"),
        team=d.get("team"),
    )


def parse_planner_response(content: str) -> PlannerResponse:
    """Parse the JSON object { scratchpad, tasks[] } from an LLM response.

    Handles:
    - Clean JSON
    - JSON wrapped in markdown fences
    - JSON with literal newlines in strings
    - Truncated JSON (salvage individual task objects)
    - Bare task arrays (no scratchpad key)
    """
    try:
        cleaned = _strip_markdown_fences(content.strip())

        obj_start = cleaned.find("{")
        obj_end = cleaned.rfind("}")
        if obj_start != -1 and obj_end > obj_start:
            candidate = cleaned[obj_start:obj_end + 1]

            # Try direct parse first, then repair.
            parsed = _try_json_loads(candidate)
            if parsed is None:
                repaired = _repair_json(candidate)
                parsed = _try_json_loads(repaired)

            if (
                isinstance(parsed, dict)
                and isinstance(parsed.get("tasks", None), list)
            ):
                return PlannerResponse(
                    scratchpad=parsed.get("scratchpad", ""),
                    tasks=[_dict_to_raw(t) for t in parsed["tasks"] if isinstance(t, dict)],
                )
    except Exception:
        pass

    # Salvage from truncated/malformed.
    salvaged = _salvage_truncated_response(content)
    if salvaged.tasks:
        logger.warning(
            "Salvaged %d tasks from malformed LLM response (len=%d)",
            len(salvaged.tasks),
            len(content),
        )
        return salvaged

    # Last resort: try parsing as a bare task array.
    try:
        tasks = parse_llm_task_array(content)
        return PlannerResponse(scratchpad="", tasks=tasks)
    except Exception:
        logger.warning("Failed to parse planner response: %s...", content[:300])
        return PlannerResponse(scratchpad="", tasks=[])


def parse_llm_task_array(content: str) -> list[RawTaskInput]:
    """Parse a bare JSON array of task objects from an LLM response."""
    cleaned = content.strip()

    # Strip fences.
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        last_bt = cleaned.rfind("```")
        if first_nl != -1 and last_bt > first_nl:
            cleaned = cleaned[first_nl + 1:last_bt].strip()

    arr_start = cleaned.find("[")
    arr_end = cleaned.rfind("]")
    if arr_start != -1 and arr_end > arr_start:
        cleaned = cleaned[arr_start:arr_end + 1]

    parsed = _try_json_loads(cleaned)
    if parsed is None:
        repaired = _repair_json(cleaned)
        parsed = json.loads(repaired)

    if not isinstance(parsed, list):
        raise ValueError("LLM response is not an array")

    return [_dict_to_raw(t) for t in parsed if isinstance(t, dict)]


# ---------------------------------------------------------------------------
# Worker response parsing
# ---------------------------------------------------------------------------

def parse_worker_response(content: str, task_id: str) -> WorkerResult:
    """Parse the structured worker JSON response: { handoff, file_operations }.

    Handles:
    - Clean JSON
    - JSON with literal newlines in strings (common with code content)
    - JSON wrapped in markdown fences
    - Truncated JSON (salvages individual file operations)
    """
    cleaned = _strip_markdown_fences(content.strip())

    # Find outermost JSON object.
    obj_start = cleaned.find("{")
    obj_end = cleaned.rfind("}")
    if obj_start == -1 or obj_end <= obj_start:
        logger.error("Worker response has no JSON object for task %s", task_id)
        return _make_failure_result(task_id, "No JSON object in worker response")

    candidate = cleaned[obj_start:obj_end + 1]

    # Try direct parse first.
    parsed = _try_json_loads(candidate)

    # If direct fails, try JSON repair (handles literal newlines in strings).
    if parsed is None:
        logger.debug("Worker JSON direct parse failed for %s — attempting repair", task_id)
        repaired = _repair_json(candidate)
        parsed = _try_json_loads(repaired)

    # If repair also fails, try salvage.
    if parsed is None:
        logger.warning("Worker JSON repair failed for %s — attempting salvage", task_id)
        return _salvage_worker_response(content, task_id)

    if not isinstance(parsed, dict):
        logger.warning("Worker response is not a dict for %s — attempting salvage", task_id)
        return _salvage_worker_response(content, task_id)

    handoff_raw = parsed.get("handoff", {})
    file_ops_raw = parsed.get("file_operations", [])

    # Build handoff — coerce all list items to str to prevent join() crashes.
    handoff = Handoff(
        task_id=task_id,
        status=handoff_raw.get("status", "complete"),
        summary=handoff_raw.get("summary", ""),
        files_changed=[str(f) for f in handoff_raw.get("files_changed", [])],
        concerns=[str(c) for c in handoff_raw.get("concerns", [])],
        suggestions=[str(s) for s in handoff_raw.get("suggestions", [])],
    )

    # Build file operations.
    file_operations: list[FileOperation] = []
    for op in file_ops_raw:
        if isinstance(op, dict) and "path" in op and "content" in op:
            file_operations.append(FileOperation(path=op["path"], content=op["content"]))

    return WorkerResult(handoff=handoff, file_operations=file_operations)


def _salvage_worker_response(content: str, task_id: str) -> WorkerResult:
    """Try to extract whatever we can from a malformed worker response.

    Uses multiple strategies:
    1. Brace-matching within file_operations array, with per-object repair
    2. Regex extraction as fallback
    """
    file_operations: list[FileOperation] = []

    # Strategy 1: Brace-match individual objects inside file_operations.
    fo_match = re.search(r'"file_operations"\s*:\s*\[', content)
    if fo_match:
        remainder = content[fo_match.end():]
        depth = 0
        obj_start = -1
        i = 0
        in_string = False

        while i < len(remainder):
            ch = remainder[i]

            if in_string:
                if ch == '\\' and i + 1 < len(remainder):
                    i += 2
                    continue
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == '{':
                    if depth == 0:
                        obj_start = i
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and obj_start != -1:
                        obj_str = remainder[obj_start:i + 1]
                        raw = _try_json_loads(obj_str)
                        if raw is None:
                            repaired_obj = _repair_json(obj_str)
                            raw = _try_json_loads(repaired_obj)
                        if isinstance(raw, dict) and "path" in raw and "content" in raw:
                            file_operations.append(
                                FileOperation(path=raw["path"], content=raw["content"])
                            )
                        obj_start = -1
                elif ch == ']' and depth == 0:
                    break

            i += 1

    # Strategy 2: Fallback regex for simple cases.
    if not file_operations:
        for m in re.finditer(r'\{\s*"path"\s*:\s*"([^"]+)"\s*,\s*"content"\s*:\s*"', content):
            path = m.group(1)
            start = m.end()
            end = _find_string_end(content, start)
            if end > start:
                raw_content = content[start:end]
                try:
                    decoded = json.loads(f'"{raw_content}"')
                except Exception:
                    decoded = raw_content.replace('\\n', '\n').replace('\\t', '\t')
                file_operations.append(FileOperation(path=path, content=decoded))

    # Try to extract handoff info.
    status = "partial" if file_operations else "failed"
    summary = f"Salvaged {len(file_operations)} file operations from malformed response"

    h_match = re.search(r'"status"\s*:\s*"([^"]+)"', content)
    if h_match:
        status = h_match.group(1)
    s_match = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', content)
    if s_match:
        try:
            summary = json.loads(f'"{s_match.group(1)}"')
        except Exception:
            summary = s_match.group(1)

    logger.info(
        "Salvaged %d file operations from malformed worker response for %s",
        len(file_operations),
        task_id,
    )

    return WorkerResult(
        handoff=Handoff(
            task_id=task_id,
            status=status,
            summary=summary,
            files_changed=[op.path for op in file_operations],
            concerns=["Worker response was malformed — salvaged what was possible"],
        ),
        file_operations=file_operations,
    )


def _find_string_end(text: str, start: int) -> int:
    """Find the end of a JSON string value starting at `start` (after opening quote)."""
    i = start
    while i < len(text):
        ch = text[i]
        if ch == '\\':
            i += 2
            continue
        if ch == '"':
            return i
        i += 1
    return len(text)


def _make_failure_result(task_id: str, reason: str) -> WorkerResult:
    return WorkerResult(
        handoff=Handoff(
            task_id=task_id,
            status="failed",
            summary=reason,
            concerns=[reason],
        ),
        file_operations=[],
    )
