from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_futures_call_put(
    futures_price: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
) -> tuple[float, float]:
    if futures_price <= 0 or strike <= 0:
        return 0.0, 0.0

    t = max(time_to_expiry, 1e-9)
    sigma = max(volatility, 1e-6)
    sqrt_t = math.sqrt(t)

    d1 = (math.log(futures_price / strike) + 0.5 * sigma * sigma * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t

    discount = math.exp(-risk_free_rate * t)
    call = discount * (futures_price * _norm_cdf(d1) - strike * _norm_cdf(d2))
    put = discount * (strike * _norm_cdf(-d2) - futures_price * _norm_cdf(-d1))
    return max(call, 0.0), max(put, 0.0)
