from __future__ import annotations

import ast
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class ParsedResponse:
    type: Literal["text", "code", "action"]
    content: str
    language: str = ""


@dataclass(frozen=True)
class CodeBlock:
    language: str
    content: str


@dataclass(frozen=True)
class StrategyValidation:
    code: str
    valid: bool
    class_name: str | None
    errors: list[str]


@dataclass(frozen=True)
class ActionParseResult:
    actions: list[dict[str, Any]]
    errors: list[str]


CODE_BLOCK_RE = re.compile(r"```([^\n`]*)\n?([\s\S]*?)```")
ACTION_BLOCK_LANGUAGE = "rewind-action"
ACTION_TYPES = {"apply_code", "run_backtest", "compare_runs", "create_strategy_and_run"}
ACTION_LABELS = {
    "apply_code": "Apply generated code",
    "run_backtest": "Run backtest",
    "compare_runs": "Compare runs",
    "create_strategy_and_run": "Create strategy and run backtest",
}


def parse_response(text: str) -> list[ParsedResponse]:
    segments: list[ParsedResponse] = []
    parts = re.split(r"(```[\s\S]*?```)", text)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("```"):
            language_match = re.match(r"^```([^\n`]*)\n?", part)
            language = language_match.group(1).strip().lower() if language_match else ""
            code = re.sub(r"^```[^\n`]*\n?", "", part)
            code = re.sub(r"\n?```$", "", code)
            segment_type: Literal["code", "action"] = (
                "action" if language == ACTION_BLOCK_LANGUAGE else "code"
            )
            segments.append(ParsedResponse(type=segment_type, content=code, language=language))
        else:
            segments.append(ParsedResponse(type="text", content=part))

    return segments


def extract_code_blocks(text: str) -> list[CodeBlock]:
    blocks: list[CodeBlock] = []
    for match in CODE_BLOCK_RE.finditer(text):
        language = match.group(1).strip().lower()
        content = match.group(2).strip()
        if content:
            blocks.append(CodeBlock(language=language, content=content))
    return blocks


def extract_python_code_blocks(text: str) -> list[str]:
    return [
        block.content
        for block in extract_code_blocks(text)
        if block.language in {"python", "py"}
    ]


def validate_generated_strategy_response(text: str) -> StrategyValidation | None:
    python_blocks = extract_python_code_blocks(text)
    if not python_blocks:
        return None

    if len(python_blocks) != 1:
        return StrategyValidation(
            code="\n\n".join(python_blocks),
            valid=False,
            class_name=None,
            errors=["Expected exactly one fenced python strategy code block."],
        )

    return validate_generated_strategy_code(python_blocks[0])


def parse_assistant_actions(
    text: str,
    generated_strategy: StrategyValidation | None = None,
) -> ActionParseResult:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []

    for block_index, block in enumerate(extract_code_blocks(text), start=1):
        if block.language != ACTION_BLOCK_LANGUAGE:
            continue

        try:
            raw_block = json.loads(block.content)
        except json.JSONDecodeError as exc:
            errors.append(f"Action block {block_index} is not valid JSON: {exc.msg}.")
            continue

        if not isinstance(raw_block, dict):
            errors.append(f"Action block {block_index} must be a JSON object.")
            continue

        raw_actions = raw_block.get("actions")
        if not isinstance(raw_actions, list):
            errors.append(f"Action block {block_index} must contain an actions array.")
            continue

        for action_index, raw_action in enumerate(raw_actions, start=1):
            action, action_errors = _normalize_action(
                raw_action,
                block_index,
                action_index,
                generated_strategy,
            )
            errors.extend(action_errors)
            if action is not None:
                actions.append(action)

    return ActionParseResult(actions=actions, errors=errors)


def validate_generated_strategy_code(code: str) -> StrategyValidation:
    errors: list[str] = []
    class_name: str | None = None

    try:
        tree = ast.parse(code)
        compile(tree, "<generated_strategy>", "exec")
    except SyntaxError as exc:
        message = exc.msg
        if exc.lineno is not None:
            message = f"{message} at line {exc.lineno}"
        return StrategyValidation(code=code, valid=False, class_name=None, errors=[message])

    strategy_classes = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and _extends_strategy(node)
    ]

    if len(strategy_classes) != 1:
        errors.append("Expected exactly one class that extends Strategy.")
    else:
        strategy_class = strategy_classes[0]
        class_name = strategy_class.name
        method_names = {
            item.name
            for item in strategy_class.body
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        for required_method in ("init", "next"):
            if required_method not in method_names:
                errors.append(f"{strategy_class.name} must define {required_method}().")

    return StrategyValidation(
        code=code,
        valid=not errors,
        class_name=class_name,
        errors=errors,
    )


def _normalize_action(
    raw_action: Any,
    block_index: int,
    action_index: int,
    generated_strategy: StrategyValidation | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    prefix = f"Action block {block_index}, action {action_index}"
    errors: list[str] = []

    if not isinstance(raw_action, dict):
        return None, [f"{prefix} must be an object."]

    action_type = raw_action.get("type")
    if action_type not in ACTION_TYPES:
        return None, [f"{prefix} has unsupported type."]

    action_id = raw_action.get("id")
    if action_id is None or action_id == "":
        normalized_id = str(uuid.uuid4())
    else:
        normalized_id = _parse_uuid(action_id, f"{prefix} id", errors)

    payload = raw_action.get("payload")
    if not isinstance(payload, dict):
        return None, [*errors, f"{prefix} payload must be an object."]

    normalized_payload: dict[str, Any] | None = None
    if action_type == "apply_code":
        normalized_payload = _normalize_apply_code_payload(
            payload,
            generated_strategy,
            prefix,
            errors,
        )
    elif action_type == "run_backtest":
        normalized_payload = _normalize_run_backtest_payload(payload, prefix, errors)
    elif action_type == "compare_runs":
        normalized_payload = _normalize_compare_runs_payload(payload, prefix, errors)
    elif action_type == "create_strategy_and_run":
        normalized_payload = _normalize_create_strategy_and_run_payload(
            payload,
            generated_strategy,
            prefix,
            errors,
        )

    if normalized_id is None or normalized_payload is None or errors:
        return None, errors

    label = raw_action.get("label")
    normalized_label = label.strip() if isinstance(label, str) and label.strip() else ""

    return (
        {
            "id": normalized_id,
            "type": action_type,
            "label": normalized_label or ACTION_LABELS[action_type],
            "status": "proposed",
            "payload": normalized_payload,
        },
        [],
    )


def _normalize_apply_code_payload(
    payload: dict[str, Any],
    generated_strategy: StrategyValidation | None,
    prefix: str,
    errors: list[str],
) -> dict[str, Any] | None:
    strategy_id = _parse_uuid(payload.get("strategy_id"), f"{prefix} payload.strategy_id", errors)
    raw_code = payload.get("code")
    raw_class_name = payload.get("class_name")

    if isinstance(raw_code, str) and raw_code.strip():
        code = raw_code.strip()
        validation = validate_generated_strategy_code(code)
        if not validation.valid:
            errors.extend(f"{prefix} payload.code {error}" for error in validation.errors)
            return None
        class_name = raw_class_name if isinstance(raw_class_name, str) else validation.class_name
    elif generated_strategy is not None and generated_strategy.valid:
        code = generated_strategy.code
        class_name = (
            raw_class_name if isinstance(raw_class_name, str) else generated_strategy.class_name
        )
    else:
        errors.append(
            f"{prefix} apply_code requires payload.code or one valid generated strategy block."
        )
        return None

    if strategy_id is None:
        return None

    normalized: dict[str, Any] = {"strategy_id": strategy_id, "code": code}
    if isinstance(class_name, str) and class_name:
        normalized["class_name"] = class_name
    return normalized


def _normalize_run_backtest_payload(
    payload: dict[str, Any],
    prefix: str,
    errors: list[str],
) -> dict[str, Any] | None:
    strategy_id = _parse_uuid(payload.get("strategy_id"), f"{prefix} payload.strategy_id", errors)
    params = payload.get("params", {})
    if not isinstance(params, dict):
        errors.append(f"{prefix} payload.params must be an object when provided.")
        return None

    if strategy_id is None:
        return None

    return {"strategy_id": strategy_id, "params": params}


def _normalize_compare_runs_payload(
    payload: dict[str, Any],
    prefix: str,
    errors: list[str],
) -> dict[str, Any] | None:
    raw_run_ids = payload.get("run_ids")
    if not isinstance(raw_run_ids, list):
        errors.append(f"{prefix} payload.run_ids must be an array.")
        return None

    run_ids: list[str] = []
    seen_run_ids: set[str] = set()
    for index, raw_run_id in enumerate(raw_run_ids):
        run_id = _parse_uuid(raw_run_id, f"{prefix} payload.run_ids[{index}]", errors)
        if run_id is None or run_id in seen_run_ids:
            continue
        seen_run_ids.add(run_id)
        run_ids.append(run_id)

    if len(run_ids) < 2:
        errors.append(f"{prefix} compare_runs requires at least two unique run IDs.")
        return None

    return {"run_ids": run_ids}


def _normalize_create_strategy_and_run_payload(
    payload: dict[str, Any],
    generated_strategy: StrategyValidation | None,
    prefix: str,
    errors: list[str],
) -> dict[str, Any] | None:
    name = _parse_non_empty_string(payload.get("name"), f"{prefix} payload.name", errors)
    raw_description = payload.get("description", "")
    description = raw_description.strip() if isinstance(raw_description, str) else ""
    if not isinstance(raw_description, str):
        errors.append(f"{prefix} payload.description must be a string when provided.")

    params = payload.get("params", {})
    if not isinstance(params, dict):
        errors.append(f"{prefix} payload.params must be an object when provided.")
        return None

    raw_code = payload.get("code")
    raw_class_name = payload.get("class_name")
    code = ""
    class_name: str | None = None

    if isinstance(raw_code, str) and raw_code.strip():
        validation = validate_generated_strategy_code(raw_code.strip())
        if not validation.valid:
            errors.extend(f"{prefix} payload.code {error}" for error in validation.errors)
            return None
        code = validation.code.strip()
        class_name = raw_class_name if isinstance(raw_class_name, str) else validation.class_name
    elif generated_strategy is not None and generated_strategy.valid:
        code = generated_strategy.code.strip()
        class_name = (
            raw_class_name if isinstance(raw_class_name, str) else generated_strategy.class_name
        )
    else:
        errors.append(
            f"{prefix} create_strategy_and_run requires payload.code or one valid generated strategy block."
        )
        return None

    if name is None or errors:
        return None

    normalized: dict[str, Any] = {
        "name": name,
        "description": description,
        "code": code,
        "params": params,
    }
    if isinstance(class_name, str) and class_name:
        normalized["class_name"] = class_name
    return normalized


def _parse_uuid(value: Any, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str):
        errors.append(f"{field} must be a UUID string.")
        return None

    try:
        return str(uuid.UUID(value))
    except ValueError:
        errors.append(f"{field} must be a valid UUID.")
        return None


def _parse_non_empty_string(value: Any, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str):
        errors.append(f"{field} must be a string.")
        return None

    normalized = value.strip()
    if not normalized:
        errors.append(f"{field} cannot be empty.")
        return None
    return normalized


def _extends_strategy(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Strategy":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Strategy":
            return True
    return False
