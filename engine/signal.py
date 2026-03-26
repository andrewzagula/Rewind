from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    reason: str = field(default="")
