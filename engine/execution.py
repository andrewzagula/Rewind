"""Execution model: how signals turn into fills, and what they cost.

The defaults describe a conservative US retail account trading liquid stocks:

- Orders fill at the next bar's open, not the close of the bar that produced the signal.
- A small slippage percentage moves every fill against you.
- Broker commission is zero, but the regulatory fees charged on every sale are included
  (SEC Section 31 fee and FINRA Trading Activity Fee).
- Buys are limited to what the account can pay for, and sells to what it holds.

Pass ``params["execution"] = "ideal"`` (or ``{"preset": "ideal"}``) to reproduce the older
frictionless behaviour: fills at the close, no costs, no cash or position checks.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields, replace
from typing import Any, Literal

FillMode = Literal["next_open", "close"]

FILL_MODES = ("next_open", "close")
PRESET_NAMES = ("realistic", "ideal")

# SEC Section 31 fee: $27.80 per $1,000,000 of sale proceeds (rate is adjusted periodically).
DEFAULT_SEC_FEE_RATE = 27.80 / 1_000_000
# FINRA Trading Activity Fee: $0.000166 per share sold, capped at $8.30 per trade.
DEFAULT_FINRA_TAF_PER_SHARE = 0.000166
DEFAULT_FINRA_TAF_MAX = 8.30


class ExecutionConfigError(ValueError):
    """Raised when run params describe an invalid execution configuration."""


@dataclass(frozen=True)
class FeeBreakdown:
    commission: float = 0.0
    regulatory: float = 0.0

    @property
    def total(self) -> float:
        return self.commission + self.regulatory


@dataclass(frozen=True)
class ExecutionConfig:
    fill_mode: str = "next_open"
    slippage_pct: float = 0.0005
    commission_per_trade: float = 0.0
    commission_per_share: float = 0.0
    commission_min: float = 0.0
    sec_fee_rate: float = DEFAULT_SEC_FEE_RATE
    finra_taf_per_share: float = DEFAULT_FINRA_TAF_PER_SHARE
    finra_taf_max: float = DEFAULT_FINRA_TAF_MAX
    enforce_cash: bool = True
    allow_partial_fills: bool = True
    allow_short: bool = False

    # ----- presets -------------------------------------------------------------------

    @classmethod
    def realistic(cls) -> ExecutionConfig:
        return cls()

    @classmethod
    def ideal(cls) -> ExecutionConfig:
        return cls(
            fill_mode="close",
            slippage_pct=0.0,
            commission_per_trade=0.0,
            commission_per_share=0.0,
            commission_min=0.0,
            sec_fee_rate=0.0,
            finra_taf_per_share=0.0,
            finra_taf_max=0.0,
            enforce_cash=False,
            allow_partial_fills=False,
            allow_short=True,
        )

    @classmethod
    def from_preset(cls, name: str) -> ExecutionConfig:
        normalized = (name or "").strip().lower()
        if normalized == "ideal":
            return cls.ideal()
        if normalized in {"", "realistic", "default", "custom"}:
            return cls.realistic()
        raise ExecutionConfigError(
            f"Unknown execution preset {name!r}; expected one of {', '.join(PRESET_NAMES)}."
        )

    @classmethod
    def from_params(cls, params: dict[str, Any] | None) -> ExecutionConfig:
        """Build a config from ``params["execution"]``.

        Accepts a preset name, or an object with an optional ``preset`` plus any field
        overrides. Missing keys fall back to the preset. Unknown keys and bad values raise
        ``ExecutionConfigError``.
        """
        raw = (params or {}).get("execution")
        if raw is None:
            return cls.realistic()
        if isinstance(raw, str):
            return cls.from_preset(raw)
        if not isinstance(raw, dict):
            raise ExecutionConfigError("params.execution must be a preset name or an object.")

        preset_name = raw.get("preset", "realistic")
        if not isinstance(preset_name, str):
            raise ExecutionConfigError("params.execution.preset must be a string.")
        config = cls.from_preset(preset_name)

        known = {field.name: field for field in fields(cls)}
        overrides: dict[str, Any] = {}
        for key, value in raw.items():
            if key == "preset":
                continue
            if key not in known:
                raise ExecutionConfigError(f"Unknown execution setting {key!r}.")
            overrides[key] = _coerce(key, value, known[key].type)
        config = replace(config, **overrides)
        config.validate()
        return config

    def validate(self) -> None:
        if self.fill_mode not in FILL_MODES:
            raise ExecutionConfigError(
                f"fill_mode must be one of {', '.join(FILL_MODES)}, not {self.fill_mode!r}."
            )
        if not 0 <= self.slippage_pct < 0.5:
            raise ExecutionConfigError("slippage_pct must be between 0 and 0.5 (0.5 = 50%).")
        for name in (
            "commission_per_trade",
            "commission_per_share",
            "commission_min",
            "sec_fee_rate",
            "finra_taf_per_share",
            "finra_taf_max",
        ):
            if getattr(self, name) < 0:
                raise ExecutionConfigError(f"{name} cannot be negative.")

    # ----- description -----------------------------------------------------------------

    @property
    def preset(self) -> str:
        if self == ExecutionConfig.ideal():
            return "ideal"
        if self == ExecutionConfig.realistic():
            return "realistic"
        return "custom"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {"preset": self.preset, **data}

    # ----- pricing ---------------------------------------------------------------------

    def fill_price(self, side: str, reference_price: float) -> float:
        """Move the reference price against the trader by the slippage percentage."""
        if side == "buy":
            return reference_price * (1.0 + self.slippage_pct)
        return reference_price * (1.0 - self.slippage_pct)

    def fees(self, side: str, quantity: float, price: float) -> FeeBreakdown:
        if quantity <= 0:
            return FeeBreakdown()
        commission = self.commission_per_trade + self.commission_per_share * quantity
        if commission > 0:
            commission = max(commission, self.commission_min)
        regulatory = 0.0
        if side == "sell":
            proceeds = quantity * price
            regulatory += proceeds * self.sec_fee_rate
            taf = quantity * self.finra_taf_per_share
            if self.finra_taf_max > 0:
                taf = min(taf, self.finra_taf_max)
            regulatory += taf
        return FeeBreakdown(commission=round(commission, 6), regulatory=round(regulatory, 6))

    def affordable_quantity(self, cash: float, price: float, requested: float) -> float:
        """Largest quantity up to ``requested`` whose cost including fees fits in ``cash``."""
        if price <= 0 or cash <= 0:
            return 0.0
        whole_shares = float(requested).is_integer()
        quantity = min(requested, (cash - self.commission_per_trade) / price)
        if whole_shares:
            quantity = float(math.floor(quantity))
        for _ in range(64):
            if quantity <= 0:
                return 0.0
            cost = quantity * price + self.fees("buy", quantity, price).total
            if cost <= cash + 1e-9:
                return quantity
            quantity = quantity - 1 if whole_shares else quantity * (cash / cost) * 0.999
        return 0.0


def _coerce(key: str, value: Any, annotation: Any) -> Any:
    kind = str(annotation)
    if "bool" in kind:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise ExecutionConfigError(f"{key} must be true or false.")
    if "float" in kind:
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise ExecutionConfigError(f"{key} must be a number.")
        try:
            number = float(value)
        except ValueError as exc:
            raise ExecutionConfigError(f"{key} must be a number.") from exc
        if math.isnan(number) or math.isinf(number):
            raise ExecutionConfigError(f"{key} must be a finite number.")
        return number
    if not isinstance(value, str):
        raise ExecutionConfigError(f"{key} must be a string.")
    return value.strip().lower()
