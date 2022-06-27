"""
Strategies for what to do with the position on each epoch.
"""
import numpy as np
import pandas as pd
from strategies.core import add_liquidity, remove_liquidity
from typing import Tuple


class TradingStrategy:
    def __init__(self) -> None:
        pass

    def execute(self):
        raise NotImplementedError


class HODLStrategy(TradingStrategy):
    """
    Pass through strategy. HODL. No change over time.
    """

    def __init__(self) -> None:
        super().__init__()

    def execute(
        self,
        token_supply: Tuple[float, float],
        token_debt: Tuple[float, float],
        df: pd.DataFrame,
        input_cash: float = None,
    ) -> Tuple[Tuple[float, float], Tuple[float, float], float, float, float]:
        """
        Passthrough
        Return: token_supply, token_debt, cash, fees, metadata
        """
        return token_supply, token_debt, input_cash, 0, dict()


class RebalanceStrategy(TradingStrategy):
    """
    Simple rebalancing strategy that rebalances when the current price moves up or
    down X% from the anchor.
    For simplicity, the rebalance isn't doing fancy math to add or remove collateral.
    It's just closing the position and re-opening. Normally fees are higher by doing
    that, but they can be dampened by adjusting fee_* during initialization.
    """

    def __init__(
        self,
        price_anchor: float,
        threshold: float,
        leverage: float,
        amount: float = 1.0,
        fee_swap: float = 0.003,
        fee_gas: float = 0.0,
    ) -> None:
        super().__init__()
        self._price_anchor = price_anchor
        self._threshold = threshold
        self._leverage = leverage
        self._amount = amount
        self._fee_swap = fee_swap
        self._fee_gas = fee_gas
        self._initial_price = price_anchor

    def execute(
        self,
        token_supply: Tuple[float, float],
        token_debt: Tuple[float, float],
        df: pd.DataFrame,
        input_cash: float = None,
    ) -> Tuple[Tuple[float, float], Tuple[float, float], float, float, float]:
        """
        Execute strategy.
        df is the main dataframe up to current date

        Return: token_supply, token_debt, cash, fees, metadata
        """

        # Get most recent price from data table
        token0_price = df.iloc[-1]["token0_price"]
        token1_price = df.iloc[-1]["token1_price"]
        pool_prices = [token0_price, token1_price]
        metadata = dict()

        # Init
        # No change in cash since we re-open with the cash aquired from closure
        output_cash = input_cash
        fees = 0

        # Check deviation
        price_delta = np.abs(token1_price - self._price_anchor) / self._price_anchor
        metadata["price_delta"] = price_delta  # Assign output metadata

        # Rebalance if deviation exceeds threshold
        if price_delta > self._threshold:
            print(
                f"Price Delta {price_delta} exceeded threshold {self._threshold}. "
                f"cur_price={token1_price}, anchor_price={self._price_anchor}. "
                f"Rebalancing."
            )

            # Close the position
            token_supply, token_debt, cash_close, fees_close = remove_liquidity(
                token_supply,
                token_debt,
                pool_prices,
                self._amount,
                self._fee_swap,
                self._fee_gas,
            )

            # Re-open the position
            token_supply, token_debt, fees_open = add_liquidity(
                cash_close, self._leverage, pool_prices, self._fee_swap, self._fee_gas
            )

            # Accumulate cash and fees
            fees = fees_close + fees_open

            # Update the anchor price to be current
            self._price_anchor = token1_price

        return token_supply, token_debt, output_cash, fees, metadata
