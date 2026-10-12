from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_price_per_1k: float = 0.0
    output_price_per_1k: float = 0.0


def estimate_cost(price: ModelPrice, input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1000.0) * price.input_price_per_1k + (output_tokens / 1000.0) * price.output_price_per_1k
