import json

from llm.parser import (
    extract_python_code_blocks,
    parse_assistant_actions,
    parse_response,
    validate_generated_strategy_response,
)

VALID_STRATEGY_CODE = """from engine import Signal, Strategy


class MovingAverageStrategy(Strategy):
    def init(self, params: dict) -> None:
        self.window = int(params.get("window", 20))
        self.closes = []

    def next(self, row: dict, portfolio) -> Signal | None:
        self.closes.append(row["close"])
        if len(self.closes) < self.window:
            return None
        average = sum(self.closes[-self.window:]) / self.window
        if row["close"] > average and row["symbol"] not in portfolio.position_symbols:
            return Signal(symbol=row["symbol"], side="buy", quantity=10)
        return None
"""


def test_parse_text_only():
    result = parse_response("This is plain text.")
    assert len(result) == 1
    assert result[0].type == "text"


def test_parse_code_block():
    text = "Here is code:\n```python\nprint('hello')\n```\nDone."
    result = parse_response(text)
    assert len(result) == 3
    assert result[0].type == "text"
    assert result[1].type == "code"
    assert result[1].language == "python"
    assert "print" in result[1].content
    assert result[2].type == "text"


def test_parse_action_block_marks_segment_as_action():
    text = "Do this:\n```rewind-action\n{\"actions\": []}\n```"

    result = parse_response(text)

    assert len(result) == 2
    assert result[1].type == "action"
    assert result[1].language == "rewind-action"


def test_extract_python_code_blocks_ignores_non_python_blocks():
    text = "```json\n{\"x\": 1}\n```\n```python\nprint('ok')\n```"

    assert extract_python_code_blocks(text) == ["print('ok')"]


def test_validate_generated_strategy_response_accepts_valid_strategy():
    result = validate_generated_strategy_response(f"```python\n{VALID_STRATEGY_CODE}\n```")

    assert result is not None
    assert result.valid is True
    assert result.class_name == "MovingAverageStrategy"
    assert result.errors == []
    assert "class MovingAverageStrategy(Strategy)" in result.code


def test_validate_generated_strategy_response_ignores_non_python_code_blocks():
    result = validate_generated_strategy_response("```json\n{\"code\": true}\n```")

    assert result is None


def test_validate_generated_strategy_response_rejects_syntax_errors():
    result = validate_generated_strategy_response(
        "```python\nclass BrokenStrategy(Strategy)\n    pass\n```"
    )

    assert result is not None
    assert result.valid is False
    assert result.class_name is None
    assert "line 1" in result.errors[0]


def test_validate_generated_strategy_response_rejects_missing_strategy_subclass():
    result = validate_generated_strategy_response("```python\nclass Helper:\n    pass\n```")

    assert result is not None
    assert result.valid is False
    assert result.class_name is None
    assert result.errors == ["Expected exactly one class that extends Strategy."]


def test_validate_generated_strategy_response_rejects_missing_required_methods():
    result = validate_generated_strategy_response(
        "```python\nclass EmptyStrategy(Strategy):\n    pass\n```"
    )

    assert result is not None
    assert result.valid is False
    assert result.class_name == "EmptyStrategy"
    assert result.errors == [
        "EmptyStrategy must define init().",
        "EmptyStrategy must define next().",
    ]


def test_validate_generated_strategy_response_rejects_multiple_strategy_classes():
    result = validate_generated_strategy_response(
        "```python\nclass FirstStrategy(Strategy):\n    def init(self, params):\n"
        "        pass\n    def next(self, row, portfolio):\n        return None\n\n"
        "class SecondStrategy(Strategy):\n    def init(self, params):\n"
        "        pass\n    def next(self, row, portfolio):\n        return None\n```"
    )

    assert result is not None
    assert result.valid is False
    assert result.class_name is None
    assert result.errors == ["Expected exactly one class that extends Strategy."]


def test_parse_assistant_actions_accepts_valid_actions():
    strategy_id = "11111111-1111-1111-1111-111111111111"
    run_id_1 = "22222222-2222-2222-2222-222222222222"
    run_id_2 = "33333333-3333-3333-3333-333333333333"
    text = f"""
```rewind-action
{{
  "actions": [
    {{
      "type": "run_backtest",
      "label": "Run the updated strategy",
      "payload": {{
        "strategy_id": "{strategy_id}",
        "params": {{"symbol": "AAPL"}}
      }}
    }},
    {{
      "type": "compare_runs",
      "payload": {{
        "run_ids": ["{run_id_1}", "{run_id_2}", "{run_id_1}"]
      }}
    }}
  ]
}}
```
"""

    result = parse_assistant_actions(text)

    assert result.errors == []
    assert len(result.actions) == 2
    assert result.actions[0]["type"] == "run_backtest"
    assert result.actions[0]["label"] == "Run the updated strategy"
    assert result.actions[0]["status"] == "proposed"
    assert result.actions[0]["payload"] == {
        "strategy_id": strategy_id,
        "params": {"symbol": "AAPL"},
    }
    assert result.actions[1]["payload"] == {"run_ids": [run_id_1, run_id_2]}


def test_parse_assistant_actions_ignores_ordinary_json_blocks():
    text = """```json
{"actions": [{"type": "run_backtest"}]}
```"""

    result = parse_assistant_actions(text)

    assert result.actions == []
    assert result.errors == []


def test_parse_assistant_actions_reports_invalid_json():
    result = parse_assistant_actions("```rewind-action\n{\"actions\": [}\n```")

    assert result.actions == []
    assert result.errors
    assert "not valid JSON" in result.errors[0]


def test_parse_assistant_actions_rejects_invalid_uuid():
    text = """```rewind-action
{"actions": [{"type": "run_backtest", "payload": {"strategy_id": "bad"}}]}
```"""

    result = parse_assistant_actions(text)

    assert result.actions == []
    assert result.errors == ["Action block 1, action 1 payload.strategy_id must be a valid UUID."]


def test_parse_assistant_actions_resolves_apply_code_from_generated_strategy():
    strategy_id = "11111111-1111-1111-1111-111111111111"
    generated = validate_generated_strategy_response(f"```python\n{VALID_STRATEGY_CODE}\n```")
    text = f"""```python
{VALID_STRATEGY_CODE}
```

```rewind-action
{{
  "actions": [
    {{
      "type": "apply_code",
      "payload": {{"strategy_id": "{strategy_id}"}}
    }}
  ]
}}
```"""

    result = parse_assistant_actions(text, generated)

    assert result.errors == []
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action["type"] == "apply_code"
    assert action["payload"]["strategy_id"] == strategy_id
    assert action["payload"]["code"] == VALID_STRATEGY_CODE.strip()
    assert action["payload"]["class_name"] == "MovingAverageStrategy"


def test_parse_assistant_actions_accepts_create_strategy_and_run_with_code():
    text = f"""
```rewind-action
{{
  "actions": [
    {{
      "type": "create_strategy_and_run",
      "payload": {{
        "name": "Momentum Test",
        "description": "A generated momentum strategy.",
        "code": {json.dumps(VALID_STRATEGY_CODE)},
        "params": {{"symbol": "AAPL", "initial_cash": 100000}}
      }}
    }}
  ]
}}
```
"""

    result = parse_assistant_actions(text)

    assert result.errors == []
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action["type"] == "create_strategy_and_run"
    assert action["label"] == "Create strategy and run backtest"
    assert action["payload"] == {
        "name": "Momentum Test",
        "description": "A generated momentum strategy.",
        "code": VALID_STRATEGY_CODE.strip(),
        "params": {"symbol": "AAPL", "initial_cash": 100000},
        "class_name": "MovingAverageStrategy",
    }


def test_parse_assistant_actions_resolves_create_strategy_and_run_from_generated_strategy():
    generated = validate_generated_strategy_response(f"```python\n{VALID_STRATEGY_CODE}\n```")
    text = f"""```python
{VALID_STRATEGY_CODE}
```

```rewind-action
{{
  "actions": [
    {{
      "type": "create_strategy_and_run",
      "payload": {{
        "name": "Generated Momentum",
        "description": "Created from chat.",
        "params": {{"symbol": "MSFT"}}
      }}
    }}
  ]
}}
```"""

    result = parse_assistant_actions(text, generated)

    assert result.errors == []
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action["payload"]["name"] == "Generated Momentum"
    assert action["payload"]["description"] == "Created from chat."
    assert action["payload"]["code"] == VALID_STRATEGY_CODE.strip()
    assert action["payload"]["class_name"] == "MovingAverageStrategy"
    assert action["payload"]["params"] == {"symbol": "MSFT"}


def test_parse_assistant_actions_rejects_create_strategy_and_run_invalid_payload_shape():
    text = """```rewind-action
{"actions": [{"type": "create_strategy_and_run", "payload": {"description": 12, "params": []}}]}
```"""

    result = parse_assistant_actions(text)

    assert result.actions == []
    assert result.errors == [
        "Action block 1, action 1 payload.name must be a string.",
        "Action block 1, action 1 payload.description must be a string when provided.",
        "Action block 1, action 1 payload.params must be an object when provided.",
    ]


def test_parse_assistant_actions_rejects_create_strategy_and_run_invalid_code():
    text = """```rewind-action
{
  "actions": [
    {
      "type": "create_strategy_and_run",
      "payload": {
        "name": "Broken",
        "description": "",
        "code": "class Broken(Strategy):\\n    pass",
        "params": {}
      }
    }
  ]
}
```"""

    result = parse_assistant_actions(text)

    assert result.actions == []
    assert result.errors == [
        "Action block 1, action 1 payload.code Broken must define init().",
        "Action block 1, action 1 payload.code Broken must define next().",
    ]
