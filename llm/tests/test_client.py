from llm.client import accumulate_tool_call_delta, build_assistant_message, parse_tool_arguments


def test_accumulate_tool_call_delta_merges_fragments() -> None:
    store: dict = {}
    accumulate_tool_call_delta(store, 0, "call_1", "run_", None)
    accumulate_tool_call_delta(store, 0, None, "backtest", '{"strategy')
    accumulate_tool_call_delta(store, 0, None, None, '_id": "abc"}')
    accumulate_tool_call_delta(store, 1, "call_2", "list_runs", "{}")

    message = build_assistant_message("Working on it", store)

    assert message["role"] == "assistant"
    assert message["content"] == "Working on it"
    assert [call["id"] for call in message["tool_calls"]] == ["call_1", "call_2"]
    assert message["tool_calls"][0]["function"] == {
        "name": "run_backtest",
        "arguments": '{"strategy_id": "abc"}',
    }


def test_build_assistant_message_without_tools_has_no_tool_calls() -> None:
    message = build_assistant_message("", {})
    assert message == {"role": "assistant", "content": None}


def test_parse_tool_arguments_handles_bad_input() -> None:
    assert parse_tool_arguments(None) == ({}, "")
    assert parse_tool_arguments('{"a": 1}') == ({"a": 1}, "")
    arguments, error = parse_tool_arguments("[1, 2]")
    assert arguments == {} and "JSON object" in error
    arguments, error = parse_tool_arguments("{broken")
    assert arguments == {} and "not valid JSON" in error
