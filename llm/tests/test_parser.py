from llm.parser import parse_response


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
    assert "print" in result[1].content
    assert result[2].type == "text"
