"""
Strategies for what to do with accumulated rewards.
"""
from typing import Callable, Optional, Tuple


def sell_rewards(
    reward_tokens: float,
    reward_price: float,
    pool_tokens: Optional[Tuple[float, float]] = None,
    amount: float = 1.0,
    fee_swap: float = 0.003,
    fee_gas: float = 0.0,
) -> Tuple[float, Tuple[float, float], float, float]:
    if amount <= 0:
        return reward_tokens, pool_tokens, 0.0, 0.0

    # Derive rewards being sold
    reward_tokens_sell = amount * reward_tokens

    # Update rewards: Remove rewards being sold
    reward_tokens = reward_tokens - reward_tokens_sell

    # Derive tokens remaining after swap fee taken from transaction
    reward_tokens_sell_after_fees = reward_tokens_sell * (1.0 - fee_swap)

    # Sell tokens (after fee) to cash
    cash = reward_tokens_sell_after_fees * reward_price

    # Derive gas fees, accumulated separately since assumed covered by an independent
    # balance of protocol tokens
    fees = fee_gas * 1.0  # one transaction

    return reward_tokens, pool_tokens, cash, fees


class RewardsStrategy:
    """Container class to execute reward strategy"""

    def __init__(self, sell_amount: float) -> None:
        """
        Args:
            rewards_fn: Which function to exercise on each epoch.
        """
        self._rewards_sell_amount = sell_amount

    def execute(self):
        raise NotImplementedError


class SellRewardsStrategy(RewardsStrategy):
    """Sells rewards on every epoch"""

    def __init__(self, sell_amount: float) -> None:
        super().__init__(sell_amount)

    def execute(
        self,
        reward_tokens: float,
        reward_price: float,
        pool_tokens: Optional[Tuple[float, float]] = None,
        pool_prices: Optional[Tuple[float, float]] = None,
        fee_swap: float = 0.003,
        fee_gas: float = 0.0,
    ) -> Tuple[float, Tuple[float, float], float, float]:

        reward_tokens, pool_tokens, cash, fees = sell_rewards(
            reward_tokens,
            reward_price,
            pool_tokens,
            self._rewards_sell_amount,
            fee_swap,
            fee_gas,
        )

        return reward_tokens, pool_tokens, cash, fees


class CompoundRewardsStrategy(RewardsStrategy):
    """Compounds rewards on every epoch"""

    def __init__(self, rewards_fn: Callable, sell_amount: float) -> None:
        super().__init__(rewards_fn, sell_amount)

    def execute(
        self,
        reward_tokens: float,
        reward_price: float,
        pool_tokens: Optional[Tuple[float, float]] = None,
        pool_prices: Optional[Tuple[float, float]] = None,
        fee_swap: float = 0.003,
        fee_gas: float = 0.0,
    ) -> Tuple[float, Tuple[float, float], float, float]:
        if self._rewards_sell_amount <= 0:
            return reward_tokens, pool_tokens, 0.0, 0.0

        # Sell assigned self._rewards_sell_amount of rewards to cash
        reward_tokens, _, cash, fees = sell_rewards(
            reward_tokens,
            reward_price,
            None,
            self._rewards_sell_amount,
            fee_swap,
            fee_gas,
        )

        # Split cash between the two tokens, buy, and increment
        for i in [0, 1]:
            cash_swap_after_fees = 0.5 * cash * (1.0 - fee_swap)
            bought_tokens = cash_swap_after_fees / pool_prices[i]
            pool_tokens[i] += bought_tokens
        cash = 0

        # Derive gas fees, accumulated separately since assumed covered by an
        # independent balance of protocol tokens
        fees += (
            fee_gas * 2.0
        )  # two additional transactions (one for each token swap for LP pair)
        fees += (
            fee_gas * 1.0
        )  # one additional transactions (one for entry or stake into LP)

        return reward_tokens, pool_tokens, cash, fees
