from engine.strategy_validator import validate_strategy_code

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


def test_validate_strategy_code_accepts_valid_strategy() -> None:
    result = validate_strategy_code(VALID_STRATEGY_CODE)

    assert result.valid is True
    assert result.class_name == "MovingAverageStrategy"
    assert result.errors == []


def test_validate_strategy_code_rejects_syntax_errors() -> None:
    result = validate_strategy_code("class BrokenStrategy(Strategy)\n    pass")

    assert result.valid is False
    assert result.class_name is None
    assert "line 1" in result.errors[0]


def test_validate_strategy_code_rejects_missing_strategy_subclass() -> None:
    result = validate_strategy_code("class Helper:\n    pass")

    assert result.valid is False
    assert result.class_name is None
    assert result.errors == ["Expected exactly one class that extends Strategy."]


def test_validate_strategy_code_rejects_missing_required_methods() -> None:
    result = validate_strategy_code("class EmptyStrategy(Strategy):\n    pass")

    assert result.valid is False
    assert result.class_name == "EmptyStrategy"
    assert result.errors == [
        "EmptyStrategy must define init().",
        "EmptyStrategy must define next().",
    ]


def test_validate_strategy_code_rejects_multiple_strategy_classes() -> None:
    result = validate_strategy_code(
        "class FirstStrategy(Strategy):\n"
        "    def init(self, params):\n"
        "        pass\n"
        "    def next(self, row, portfolio):\n"
        "        return None\n\n"
        "class SecondStrategy(Strategy):\n"
        "    def init(self, params):\n"
        "        pass\n"
        "    def next(self, row, portfolio):\n"
        "        return None\n"
    )

    assert result.valid is False
    assert result.class_name is None
    assert result.errors == ["Expected exactly one class that extends Strategy."]


def test_validate_strategy_code_rejects_dangerous_imports() -> None:
    result = validate_strategy_code(
        "import os\n"
        "from engine import Strategy\n\n"
        "class FileStrategy(Strategy):\n"
        "    def init(self, params):\n"
        "        pass\n"
        "    def next(self, row, portfolio):\n"
        "        return None\n"
    )

    assert result.valid is False
    assert "Importing 'os' is not allowed in strategy code." in result.errors


def test_validate_strategy_code_rejects_dangerous_calls() -> None:
    result = validate_strategy_code(
        "from engine import Strategy\n\n"
        "class FileStrategy(Strategy):\n"
        "    def init(self, params):\n"
        "        open('/tmp/data.txt')\n"
        "    def next(self, row, portfolio):\n"
        "        return None\n"
    )

    assert result.valid is False
    assert "Calling 'open' is not allowed in strategy code." in result.errors
