"""
Contains the main functionality to execute the simulation, given
pre-configured:

- scenario
- reward strategy
- trading strategy
"""
import numpy as np
import pandas as pd
from strategies.core import add_liquidity
from strategies.rewards import RewardsStrategy
from strategies.trading import TradingStrategy
from typing import Optional
from util import iloss_amt


def enrich_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create the columns we will fill in iteratively.
    """
    df = df.copy()
    cols = [
        "token0_supply_open",
        "token1_supply_open",
        "position_pool_open_dollars",
        "apy_total",
        "token0_earnings",
        "token1_earnings",
        "trading_fee_earnings_dollars",
        "reward_earnings_dollars",
        "reward_token_earnings",
        "cash_from_rewards",
        "token0_supply_close",
        "token1_supply_close",
        "token0_debt_close",
        "token1_debt_close",
        "pool_value",
        "cash_value",
        "rewards_value",
        "fees_value",
        "position_value",
        "debt_value",
        "equity_value",
        "effective_leverage",
        "pool_equity",
        "profit_value",
        "roi",
        "annualized_apr",
        "debt_ratio",
        "iloss",
        "position_hodl_dollars",
        "trade_event",
        "strategy_metadata",
    ]
    df[cols] = np.nan
    df["trade_event"] = False
    return df


def simulate(
    df: pd.DataFrame,
    strategy_cls: TradingStrategy,
    rewards_cls: RewardsStrategy,
    initial_cap: float,
    leverage: float,
    fee_gas: float = 0.0,
    fee_swap: float = 0.003,
    reward_token_price: Optional[float] = None,
    apy_trading_fee: Optional[float] = None,
    apy_reward: Optional[float] = None,
    apy_borrow_token0: Optional[float] = None,
    apy_borrow_token1: Optional[float] = None,
    open_on_start: bool = True,
) -> pd.DataFrame:
    """
    Executes simulation given various pre-defined methods/classes/data.
    TODO: Fill in

    Args:
        df: initialized scenario from scenarios module
        strategy_cls: trading strategy object from trading module
            (or other related modules)
        rewards_cls: reward strategy object function from rewards module
        initial_cap: Initial capital for simulation
        leverage: Leverage to apply. Options: [1.0, 2.0, >2.0]
        fee_gas: Gas cost (dollars) for each transaction
        fee_swap: Percentage for swap fee. In form: 0.01 = 1%
        open_on_start: Flag to open a position as soon as the simulation starts
            If False, it is on strategy_cls to figure out when to open

    Returns:
        df: New dataframe with original data + performance results for every step

    """
    # Create a copy for this function execution
    df = df.copy()

    # Add any optional missing fields
    if "reward_token_price" not in df.columns and reward_token_price is not None:
        df["reward_token_price"] = reward_token_price
    if "apy_trading_fee" not in df.columns and apy_trading_fee is not None:
        df["apy_trading_fee"] = apy_trading_fee
    if "apy_reward" not in df.columns and apy_reward is not None:
        df["apy_reward"] = apy_reward
    if "apy_borrow_token0" not in df.columns and apy_borrow_token0 is not None:
        df["apy_borrow_token0"] = apy_borrow_token0
    if "apy_borrow_token1" not in df.columns and apy_borrow_token1 is not None:
        df["apy_borrow_token1"] = apy_borrow_token1
    df["fee_gas"] = fee_gas
    df["fee_swap"] = fee_gas

    # Add derived columns to dataframe
    df = enrich_columns(df)

    # Initialize everything
    price0_initial = df["token0_price"][0]
    price1_initial = df["token1_price"][0]
    ratio_initial = price1_initial / price0_initial
    token0_supply_initial = 0
    token1_supply_initial = 0
    token0_debt_initial = 0
    token1_debt_initial = 0
    cash_accum = initial_cap

    # Optionally open the position
    if open_on_start:
        token_supply, token_debt, fees_open = add_liquidity(
            initial_cap, leverage, [price0_initial, price1_initial], fee_swap, fee_gas
        )
        token0_supply_initial, token1_supply_initial = token_supply
        token0_debt_initial, token1_debt_initial = token_debt
        cash_accum = 0

    # Calculate the product constant of the liquidity pool
    # x = token0_supply_initial
    # y = token1_supply_initial
    # k = x * y

    """
    Calculate pool supply based on change in prices

    pre: Before daily rewards accounted for, but after impermanent loss token shift
        accounted for
    post: After daily rewards accounted for and after impermanent loss

    Ref: https://docs.google.com/spreadsheets/d/15pHFfo_Pe66VD59bTP2wsSAgK-DNE_Xic8HEIUY32uQ/edit#gid=650365.25877
        (Alpaca Finance Yield Farming Calculator)
    """  # NOQA
    # Initialize before starting loop. Recall position was already opened above.
    fees_accum = fees_open
    rewards_accum = 0
    last_token0_supply = token0_supply_initial
    last_token1_supply = token1_supply_initial
    last_token0_debt = token0_debt_initial
    last_token1_debt = token1_debt_initial
    first_date = df.iloc[0].name

    # Loop epoch-by-epoch and calculate changes over time
    for idx, row in df.iterrows():
        # Derive ratio of token B divided by token A. Provides price of A relative to B
        cur_date = row.name
        days_elapsed = (cur_date - first_date).days + 1
        token0_price = row["token0_price"]
        token1_price = row["token1_price"]
        reward_token_price = row["reward_token_price"]
        ratio = row["token1_price"] / row["token0_price"]
        apy_trading_fee = row["apy_trading_fee"]
        apy_reward = row["apy_reward"]
        fee_gas = row["fee_gas"]

        # Calculate number of tokens in pool, after impermanent loss, each step.
        tk = (
            last_token0_supply * last_token1_supply
        )  # Derive constant based on tokens in pool at close of last step
        token0_supply_open, token1_supply_open = iloss_amt(
            tk, ratio
        )  # Calculate tokens at open given impermanent loss due to new price

        # Define intermediate values that change during epoch based on strategies
        token0_supply_cur = token0_supply_open
        token1_supply_cur = token1_supply_open
        token0_debt_cur = last_token0_debt
        token1_debt_cur = last_token1_debt

        """
        Calculate positions (pre), before rewards
        """

        # Given current tokens in pool, calculate equity from the LP
        position_pool_open_dollars = (
            token0_price * token0_supply_open + token1_price * token1_supply_open
        )

        """
        Derive APYs
        """
        apy_total = apy_trading_fee + apy_reward

        """
        Calculate earnings
        """

        # Trading Fee Earnings
        # Accrue tokens in pool assuming using daily compounded trading fee APY
        # (see reference at top)
        token0_earnings = token0_supply_open * (
            apy_trading_fee / 365.25
        )  # Token0 daily increase due to trading fees
        token1_earnings = token1_supply_open * (
            apy_trading_fee / 365.25
        )  # Token1 daily increase due to trading fees
        trading_fee_earnings_dollars = (
            token0_earnings * token0_price + token1_earnings * token1_price
        )

        # Accrue
        token0_supply_cur += token0_earnings
        token1_supply_cur += token1_earnings

        # Farming Rewards
        # Assign to tokens since that's what we are rewarded in
        # Assumes rewards based on starting value of the pool, before trading fees for
        # the day
        reward_earnings_dollars = position_pool_open_dollars * apy_reward / 365.25
        reward_token_earnings = reward_earnings_dollars / reward_token_price

        """
        Calculate debt
        """
        # Debt is accrued daily in the form of number of tokens that are owed here
        # interest accrued = n_borrowed_tokens * daily_interest_rate
        # compounded continuously, ref: https://www.crunchbase.com/organization/ethlend
        token0_debt_cur = token0_debt_cur * np.exp(apy_borrow_token0 * 1.0 / 365.25)
        token1_debt_cur = token1_debt_cur * np.exp(apy_borrow_token1 * 1.0 / 365.25)

        """
        Apply reward strategy
        """

        pool_tokens_from_rewards = [0, 0]
        (
            reward_tokens_remaining,
            pool_tokens_from_rewards,
            cash_rewards,
            fees_rewards,
        ) = rewards_cls.execute(
            reward_token_earnings,
            reward_token_price,
            pool_tokens_from_rewards,
            [token0_price, token1_price],
            fee_swap=fee_swap,
            fee_gas=fee_gas,
        )

        # Accrue
        token0_supply_cur += pool_tokens_from_rewards[0]
        token1_supply_cur += pool_tokens_from_rewards[1]

        """
        Apply trading strategy
        """
        # Accumulate available cash before calling strategy
        cash_in = cash_accum + cash_rewards

        # Prep input data
        df_input = df[df.index <= idx]
        token_supply_in = [token0_supply_cur, token1_supply_cur]
        token_debt_in = [token0_debt_cur, token1_debt_cur]

        # Call trading strategy, passing through tokens/cash to be mutated
        (
            token_supply_out,
            token_debt_out,
            cash_out,
            fees_trade,
            strategy_metadata,
        ) = strategy_cls.execute(token_supply_in, token_debt_in, df_input, cash_in)

        # Track the event if a trade occurred
        trade_occurred = False
        if (token_supply_in != token_supply_out) or (token_debt_in != token_debt_out):
            trade_occurred = True

        # Accrue and finalize bookkeeping
        token0_supply_cur, token1_supply_cur = token_supply_out
        token0_debt_cur, token1_debt_cur = token_debt_out
        cash_accum = cash_out

        """
        Accumulate the other books (fees, cash, rewards)
        """

        # Accumulate
        rewards_accum += reward_tokens_remaining
        fees_accum = fees_accum + fees_rewards + fees_trade

        """
        Update token balances based on previous, trading-fee earnings, and any
        compounded rewards
        """

        # Close out using latest intermediate data
        token0_supply_close = token0_supply_cur
        token1_supply_close = token1_supply_cur
        token0_debt_close = token0_debt_cur
        token1_debt_close = token1_debt_cur

        # With owed-tokens incremented, calculate the dollar value for each
        token0_debt_value = token0_debt_close * token0_price
        token1_debt_value = token1_debt_close * token1_price

        """
        Calculate positions (post), including daily rewards
        """
        # Derive final position total
        # position includes: pool value, rewards value, cash value
        pool_value = (
            token0_price * token0_supply_close + token1_price * token1_supply_close
        )
        cash_value = cash_accum
        fees_value = fees_accum
        rewards_value = rewards_accum * reward_token_price
        position_value = (
            pool_value + rewards_value + cash_value - fees_value
        )  # Position of LP + unclaimed rewards + cash - fees incurred
        debt_value = (
            token0_debt_value + token1_debt_value
        )  # Debt from LP position borrowing
        pool_equity = pool_value - debt_value
        equity_value = position_value - debt_value  # Equity in LP positions
        profit_value = (
            equity_value - initial_cap
        )  # PnL is total gains/losses minus initial investment
        roi = profit_value / initial_cap
        debt_ratio = debt_value / (debt_value + pool_equity)
        # See francium reference. We do not include rewards or cash here since they
        # aren't in the pool.
        annualized_apr = (1.0 + (profit_value / initial_cap)) ** (
            365 / days_elapsed
        ) - 1
        effective_leverage = pool_value / pool_equity

        """
        Calulate raw impermament loss, without considering rewards
        """

        # Derive ratio now vs. what it was at start
        rel_ratio = ratio_initial / ratio

        # Calculate impermanent loss directly from relative ratios
        iloss = 2 * (rel_ratio**0.5 / (1 + rel_ratio)) - 1

        """
        Calculate HODL position as a benchmark (independent of all else above)
        """

        # Calculate what we would have had if we just HODL'd the original tokens (x, y)
        position_hodl_dollars = (
            token0_price * token0_supply_initial + token1_price * token1_supply_initial
        ) / leverage

        """
        Record current state
        """

        # Create a record of all the derived values in this epoch
        daily_record = {
            "token0_supply_open": token0_supply_open,
            "token1_supply_open": token1_supply_open,
            "position_pool_open_dollars": position_pool_open_dollars,
            "apy_total": apy_total,
            "token0_earnings": token0_earnings,
            "token1_earnings": token1_earnings,
            "trading_fee_earnings_dollars": trading_fee_earnings_dollars,
            "reward_earnings_dollars": reward_earnings_dollars,
            "reward_token_earnings": reward_token_earnings,
            "cash_from_rewards": cash_rewards,
            "token0_supply_close": token0_supply_close,
            "token1_supply_close": token1_supply_close,
            "token0_debt_close": token0_debt_close,
            "token1_debt_close": token1_debt_close,
            "pool_value": pool_value,
            "cash_value": cash_value,
            "rewards_value": rewards_value,
            "fees_value": fees_value,
            "position_value": position_value,
            "debt_value": debt_value,
            "pool_equity": pool_equity,
            "equity_value": equity_value,
            "profit_value": profit_value,
            "effective_leverage": effective_leverage,
            "roi": roi,
            "annualized_apr": annualized_apr,
            "debt_ratio": debt_ratio,
            "iloss": iloss,
            "position_hodl_dollars": position_hodl_dollars,
            "trade_event": trade_occurred,
            "strategy_metadata": strategy_metadata,
        }

        # Update the epoch in the dataframe to include these derived values
        df.loc[idx] = {**df.loc[idx].to_dict(), **daily_record}

        # Save state for next step
        last_token0_supply = token0_supply_close
        last_token1_supply = token1_supply_close
        last_token0_debt = token0_debt_close
        last_token1_debt = token1_debt_close

    return df
