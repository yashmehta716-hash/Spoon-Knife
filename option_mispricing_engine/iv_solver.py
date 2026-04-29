from __future__ import annotations

from option_mispricing_engine.pricing_model import black_scholes_futures_call_put


def implied_volatility(
    market_price: float,
    futures_price: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    option_type: str,
    max_iter: int = 100,
    tol: float = 1e-4,
) -> float | None:
    if market_price <= 0 or futures_price <= 0 or strike <= 0 or time_to_expiry <= 0:
        return None

    low, high = 1e-4, 5.0
    target_is_call = option_type.upper() == "CE"

    for _ in range(max_iter):
        mid = (low + high) / 2
        call, put = black_scholes_futures_call_put(
            futures_price=futures_price,
            strike=strike,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=mid,
        )
        model_price = call if target_is_call else put
        err = model_price - market_price

        if abs(err) <= tol:
            return mid

        if err > 0:
            high = mid
        else:
            low = mid

    return (low + high) / 2
