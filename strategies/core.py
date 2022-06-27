"""
Core actions that are agnostic to the strategy.
These can be used by the strategy.
"""
from typing import Optional, Tuple


def add_liquidity(
    capital: float,
    leverage: float,
    pool_prices: Optional[Tuple[float, float]],
    fee_swap: float = 0.003,
    fee_gas: float = 0.0,
) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """
    Opens or adds to a LP position given a predefined amount.
    Returns updated pool supply, debt, cash remaining, and fees accumulated
    All accumulative bookkeeping should happen OUTSIDE this function.
    """
    token0_price, token1_price = pool_prices
    token_supply = [0, 0]
    token_debt = [0, 0]
    fees = 0

    """
    For simplicity, we'll assume only ONE swap fee is accrued to open the position for
    all leverage levels. We'll take this off the top. Even if multiple positions are
    opened in actuality, the fee gets reduced proportionally as the capital is split.
    """
    capital = capital * (1.0 - fee_swap)

    # Open position differently based on leverage type
    if leverage == 1:
        # No leverage. Split capital in half and open a standard LP position
        # A swap is assumed here for both tokens to get balanced tokens for LP
        token0_supply = (capital / 2) / token0_price
        token1_supply = (capital / 2) / token1_price

        # Change to final format. Note: 1X is no debt
        token_supply = [token0_supply, token1_supply]
        fees = fee_gas  # Two swap gas to get the tokens + LP entry gas

    elif leverage == 2:
        """
        2X leverage is a single-position.
        Borrow 100% of principal in token1, and nothing in token0.
        """
        # Borrow by adding to debt and increasing supply by same amount
        token0_debt = 0  # No debt on base token, just NSA
        token1_debt = capital / token1_price
        token1_supply = token1_debt

        # Initial capital is used to purchase the token0-side of the pool
        token0_supply = capital / token0_price

        # Change to final format. Note: 1X is no debt
        token_supply = [token0_supply, token1_supply]
        token_debt = [token0_debt, token1_debt]
        fees = (
            4 * fee_gas
        )  # Two swap gas to get the tokens + One borrow + One LP entry gas

    elif leverage > 2:
        """
        More than 2X leverage requires two positions, or possibly a single position
        with dual-borrowing if allowed. (Ref: "Revisiting the Fundamentals of
        Pseudo-Delta Neutral Hedging")
        This aggregates tally into one single LP for bookkeeping purposes
        Ref: "Alpaca Finance Yield Farming Calculator",
        Sheet: "1.1) Pseudo delta-neutral LP farming"

        Assumes we start with principal in token0
        Example: 3X leverage @ $100, borrow ratio is L/(L-2):1, or 3:1 for 3X
        Position, total $300:
            tokenA = 0.5*principal*leverage = $150
            tokenB = 0.5*principal*leverage = $150
        Debt, total $200:
            tokenA = 0.25*principal*(leverage-1) = $50
            tokenB = 0.75*principal*(leverage-1) = $150
        """

        # Total supply ($) is leverage * initial capital. Split across tokens in LP pair
        token0_supply_value = 0.5 * leverage * capital
        token1_supply_value = 0.5 * leverage * capital

        # Derive number of tokens from those supplies
        token0_supply = token0_supply_value / token0_price
        token1_supply = token1_supply_value / token1_price

        # To open the positions that provide the supply above, we need to borrow
        # (leverage-1) dollars
        multiplier = leverage - 1

        # The ratio in which we borrow depends on the leverage amount.
        # Specifically it is a ratio of  L/(L-2):1, where the left side is the risky
        # asset
        # e.g. for 3X, it is 3:1, or 3/4 borrow risky, 1/4 borrow stable
        token0_frac = 1 / (leverage / (leverage - 2) + 1)
        token1_frac = 1.0 - token0_frac

        # Derive the debt in dollars based on above
        token0_debt_value = capital * token0_frac * multiplier
        token1_debt_value = capital * token1_frac * multiplier

        # Derive number of tokens from those debts
        token0_debt = token0_debt_value / token0_price
        token1_debt = token1_debt_value / token1_price

        # Change to final format. Note: 1X is no debt
        token_supply = [token0_supply, token1_supply]
        token_debt = [token0_debt, token1_debt]

        # Fees include: one borrow for each token (2), one swap for each borrow (2),
        # two LP pool entries (2)
        # 6 events total
        fees = 6 * fee_gas

    else:
        raise ValueError("Only supports leverage=1 or leverage>=2.")

    return token_supply, token_debt, fees


def remove_liquidity(
    token_supply: Tuple[float, float],
    token_debt: Tuple[float, float],
    pool_prices: Optional[Tuple[float, float]],
    amount: float = 1.0,
    fee_swap: float = 0.003,
    fee_gas: float = 0.0,
) -> Tuple[Tuple[float, float], Tuple[float, float], float, float]:
    """
    Fully or partially closes LP position
    Returns remaining pool supply, remaining debt, cash returned, and fees accumulated
    All accumulative bookkeeping should happen OUTSIDE this function.
    Assumes two gas events (swapping out each token).

    amount is the ratio (0-1) of total equity to sell off.

    Note: This can be vectorized or placed in loop, but left as manual/explicit to
    make the bookkeeping transparent

    """
    token0_price, token1_price = pool_prices
    token0_supply, token1_supply = token_supply
    token0_debt, token1_debt = token_debt
    fees = 0
    cash = 0

    # Determine what will remain after we remove the liquidity. Hold that aside.
    token0_supply_remaining = token0_supply * (1.0 - amount)
    token1_supply_remaining = token1_supply * (1.0 - amount)
    token0_debt_remaining = token0_debt * (1.0 - amount)
    token1_debt_remaining = token1_debt * (1.0 - amount)
    token_supply_remaining = [token0_supply_remaining, token1_supply_remaining]
    token_debt_remaining = [token0_debt_remaining, token1_debt_remaining]

    # Derive remaining tokens as well as cash accumulated based on equity
    # Token0 sell
    token0_equity = token0_supply - token0_debt
    token0_sell = token0_equity * amount
    token0_cash = token0_sell * token0_price * (1.0 - fee_swap)  # Include swap fee
    fees += fee_gas  # swap out token0

    # Token1 sell
    token1_equity = token1_supply - token1_debt
    token1_sell = token1_equity * amount
    token1_cash = token1_sell * token1_price * (1.0 - fee_swap)  # Include swap fee
    fees += fee_gas  # swap out token1

    # Determine final cash from position removal
    cash = token0_cash + token1_cash

    return token_supply_remaining, token_debt_remaining, cash, fees
