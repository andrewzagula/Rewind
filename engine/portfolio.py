from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0


@dataclass
class Portfolio:
    cash: float = 100_000.0
    positions: dict[str, Position] = field(default_factory=dict)

    @property
    def position_symbols(self) -> list[str]:
        return [s for s, p in self.positions.items() if p.quantity != 0]

    def get_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def held_quantity(self, symbol: str) -> float:
        position = self.positions.get(symbol)
        return position.quantity if position is not None else 0.0

    def update_position(
        self, symbol: str, quantity: float, price: float, fees: float = 0.0
    ) -> float:
        """Apply a fill. Positive quantity buys, negative sells.

        Buy fees are added to the position's cost basis; sell fees reduce the realized
        profit. Returns realized profit and loss (zero for buys).
        """
        pos = self.get_position(symbol)
        pnl = 0.0

        if quantity > 0:
            total_cost = pos.avg_price * pos.quantity + price * quantity + fees
            pos.quantity += quantity
            pos.avg_price = total_cost / pos.quantity if pos.quantity else 0
            self.cash -= price * quantity + fees
        else:
            sell_qty = abs(quantity)
            pnl = (price - pos.avg_price) * sell_qty - fees
            pos.quantity -= sell_qty
            self.cash += price * sell_qty - fees
            if pos.quantity == 0:
                pos.avg_price = 0.0

        return pnl

    def equity(self, prices: dict[str, float]) -> float:
        position_value = sum(
            p.quantity * prices.get(p.symbol, 0.0) for p in self.positions.values()
        )
        return self.cash + position_value
