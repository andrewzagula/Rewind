TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_strategy",
            "description": "Generate a Python trading strategy based on user description",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "indicators": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_backtest",
            "description": "Run a backtest with specified strategy and parameters",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "params": {"type": "object"},
                    "dataset_id": {"type": "string"},
                },
                "required": ["strategy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_metric",
            "description": "Explain a specific performance metric in context",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_name": {"type": "string"},
                    "value": {"type": "number"},
                },
                "required": ["metric_name"],
            },
        },
    },
]
