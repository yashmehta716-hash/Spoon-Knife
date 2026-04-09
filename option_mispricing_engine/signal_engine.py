from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SignalDecision:
    action: str
    score: float
    inefficiency_score: float
    iv_spike_pct: float
    priority: str
    reasons: list[str]


class SignalEngine:
    def __init__(
        self,
        min_volume: int,
        min_oi: int,
        max_bid_ask_spread_pct: float,
        iv_spike_threshold_pct: float,
        max_underlying_move_pct: float,
        min_option_move_pct: float,
    ) -> None:
        self.min_volume = min_volume
        self.min_oi = min_oi
        self.max_bid_ask_spread_pct = max_bid_ask_spread_pct
        self.iv_spike_threshold_pct = iv_spike_threshold_pct
        self.max_underlying_move_pct = max_underlying_move_pct
        self.min_option_move_pct = min_option_move_pct

    def evaluate(
        self,
        inefficiency_score: float,
        volume: int,
        oi: int,
        spread_pct: float | None,
        fut_change_pct: float,
        opt_change_pct: float,
        iv_spike_pct: float,
        oi_change: int,
        trend_strength: float,
    ) -> SignalDecision | None:
        reasons: list[str] = []

        if inefficiency_score > 1.0:
            action = "SELL"
        elif inefficiency_score < -0.4:
            action = "BUY"
        else:
            return None

        if volume < self.min_volume or oi < self.min_oi:
            return None
        reasons.append("liquidity")

        if spread_pct is not None and spread_pct > self.max_bid_ask_spread_pct:
            return None
        reasons.append("spread")

        if abs(fut_change_pct) > self.max_underlying_move_pct:
            return None
        if abs(opt_change_pct) < self.min_option_move_pct:
            return None
        reasons.append("underlying_stable")

        if iv_spike_pct < self.iv_spike_threshold_pct:
            return None
        reasons.append("iv_spike")

        if not (oi_change > 0 and opt_change_pct > 0):
            return None
        reasons.append("oi_confirmation")

        score = self._score(inefficiency_score, iv_spike_pct, oi_change, fut_change_pct, trend_strength)

        priority = "🟢 Mild"
        if abs(inefficiency_score) > 2.0:
            priority = "🔴 Extreme"
        elif abs(inefficiency_score) > 1.0:
            priority = "🟠 High"

        return SignalDecision(
            action=action,
            score=round(score, 2),
            inefficiency_score=inefficiency_score,
            iv_spike_pct=iv_spike_pct,
            priority=priority,
            reasons=reasons,
        )

    @staticmethod
    def _score(
        inefficiency_score: float,
        iv_spike_pct: float,
        oi_change: int,
        fut_change_pct: float,
        trend_strength: float,
    ) -> float:
        ineff_component = min(abs(inefficiency_score) * 35.0, 45.0)
        iv_component = min(iv_spike_pct * 2.2, 20.0)
        oi_component = min(max(oi_change, 0) / 2500.0 * 15.0, 15.0)
        underlying_component = max(0.0, (0.2 - abs(fut_change_pct)) / 0.2 * 10.0)
        trend_component = min(max(trend_strength, 0.0), 10.0)
        return min(100.0, ineff_component + iv_component + oi_component + underlying_component + trend_component)
