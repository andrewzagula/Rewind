from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass
class ParsedResponse:
    type: Literal["text", "code", "action"]
    content: str


def parse_response(text: str) -> list[ParsedResponse]:
    segments: list[ParsedResponse] = []
    parts = re.split(r"(```[\s\S]*?```)", text)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("```"):
            code = re.sub(r"^```\w*\n?", "", part)
            code = re.sub(r"\n?```$", "", code)
            segments.append(ParsedResponse(type="code", content=code))
        else:
            segments.append(ParsedResponse(type="text", content=part))

    return segments
