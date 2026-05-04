from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyValidation:
    code: str
    valid: bool
    class_name: str | None
    errors: list[str]


class StrategyValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(format_strategy_validation_errors(errors))


DISALLOWED_IMPORT_ROOTS = {
    "builtins",
    "ftplib",
    "http",
    "importlib",
    "multiprocessing",
    "os",
    "pathlib",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "urllib",
}

DISALLOWED_CALL_NAMES = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "globals",
    "input",
    "locals",
    "open",
}

DISALLOWED_DUNDER_NAMES = {
    "__builtins__",
    "__file__",
    "__loader__",
    "__package__",
    "__spec__",
}


def validate_strategy_code(code: str) -> StrategyValidation:
    errors: list[str] = []
    class_name: str | None = None

    try:
        tree = ast.parse(code)
        compile(tree, "<strategy>", "exec")
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

    errors.extend(_safety_errors(tree))

    return StrategyValidation(
        code=code,
        valid=not errors,
        class_name=class_name,
        errors=errors,
    )


def require_valid_strategy_code(code: str) -> StrategyValidation:
    result = validate_strategy_code(code)
    if not result.valid:
        raise StrategyValidationError(result.errors)
    return result


def format_strategy_validation_errors(errors: list[str]) -> str:
    return "Strategy code is invalid: " + "; ".join(errors)


def _safety_errors(tree: ast.AST) -> list[str]:
    errors: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".", maxsplit=1)[0]
                if root_name in DISALLOWED_IMPORT_ROOTS:
                    errors.append(f"Importing '{alias.name}' is not allowed in strategy code.")

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root_name = module.split(".", maxsplit=1)[0]
            if root_name in DISALLOWED_IMPORT_ROOTS:
                errors.append(f"Importing from '{module}' is not allowed in strategy code.")

        elif isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in DISALLOWED_CALL_NAMES:
                errors.append(f"Calling '{call_name}' is not allowed in strategy code.")
            elif "." in call_name:
                root_name = call_name.split(".", maxsplit=1)[0]
                if root_name in DISALLOWED_IMPORT_ROOTS:
                    errors.append(f"Calling '{call_name}' is not allowed in strategy code.")

        elif isinstance(node, ast.Name):
            if node.id in DISALLOWED_DUNDER_NAMES:
                errors.append(f"Accessing '{node.id}' is not allowed in strategy code.")

        elif (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("__")
            and node.attr.endswith("__")
        ):
            errors.append(f"Accessing '{node.attr}' is not allowed in strategy code.")

    return errors


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _extends_strategy(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Strategy":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Strategy":
            return True
    return False
