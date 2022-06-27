"""
Scenario generators.
Creates price, APY, etc. dataframe for use in simulation.
"""
from defaults import DEFAULT_COINDIX_HISTORY_FILE, DEFAULT_CREAM_HISTORY_FILE
from interfaces import (
    create_coingecko_price_history,
    extract_cream_borrow_apy_history_from_file,
    extract_coindix_apy_history_from_file,
)
import numpy as np
import pandas as pd
from typing import Optional
from util import random_walk


def initialize_price_dataframe(
    n_days: int,
    token0_price_initial: float,
    token1_price_initial: float,
    start_date: str = "2021-01-01",
) -> pd.DataFrame:
    """
    Creates simple dataframe with date and two token prices to use as initialization
    for scenario generators.
    """
    df = pd.DataFrame(
        (
            pd.date_range("2021-01-01", periods=n_days, freq="D"),
            n_days * [1.0],
            n_days * [token1_price_initial],
        )
    )
    df = df.T
    df = df.rename({0: "date", 1: "token0_price", 2: "token1_price"}, axis=1)
    df = df.set_index("date")
    return df


def create_no_price_change_example(
    n_days: int, token0_price: float = 1.0, token1_price: float = 0.1
) -> pd.DataFrame:
    """
    Creates a n-day table where the price remains constant. Useful for testing
    interest without IL in the mix
    """
    df = initialize_price_dataframe(n_days, token0_price, token1_price)
    return df


def create_small_example() -> pd.DataFrame:
    """
    Creates a simple input where there are 4 records.
    Records:
        1: Opening
        2: Identical to record 1, to confirm interest/appreciation without price change
        3: Asset price (token1) drops to 10% of initial value. To test calculations
            under IL.
        4: Asset price (token1) increases to 5X of initial value. To test calculations
            under IL in other direction
    """
    df = create_no_price_change_example(4, 1.0, 0.1)
    df.iloc[2, 1] = 0.01
    df.iloc[3, 1] = 0.5
    return df


def create_linear_price_change_example(
    n_days: int,
    token0_price: float = 1.0,
    token1_price_initial: float = 0.1,
    token1_price_final: float = 0.01,
    reward_token_price_initial: Optional[float] = None,
    reward_token_price_final: Optional[float] = None,
) -> pd.DataFrame:
    """
    Creates a n-day table where the both the non-safe-asset (NSA) and the reward token
    price (optionally) linearly changes over time.
    """
    df = initialize_price_dataframe(n_days, token0_price, token1_price_initial)

    # Apply the price change
    df["token1_price"] = np.linspace(token1_price_initial, token1_price_final, len(df))

    # Apply the price change
    if reward_token_price_initial and reward_token_price_final:
        df["reward_token_price"] = np.linspace(
            reward_token_price_initial, reward_token_price_final, len(df)
        )

    return df


def create_linear_and_back_example(
    n_days: int,
    token0_price: float = 1.0,
    token1_price_base: float = 0.1,
    token1_price_peak: float = 0.01,
    reward_token_price_base: Optional[float] = None,
    reward_token_price_peak: Optional[float] = None,
) -> pd.DataFrame:
    """
    Creates a n-day table where the both the non-safe-asset (NSA) and the reward token
    price (optionally) linearly changes over time. It goes from base -> peak -> return
        to base.
    """
    df = initialize_price_dataframe(n_days, token0_price, token1_price_base)

    # Apply the price change
    n = int(round(len(df) / 2)) + 1
    df["token1_price"] = np.hstack(
        (
            np.linspace(token1_price_base, token1_price_peak, n),
            np.linspace(token1_price_peak, token1_price_base, n + 1),
        )
    )[: len(df)]

    # Apply the price change
    if reward_token_price_base and reward_token_price_peak:
        df["reward_token_price"] = np.hstack(
            (
                np.linspace(reward_token_price_base, reward_token_price_peak, n),
                np.linspace(reward_token_price_peak, reward_token_price_base, n + 1),
            )
        )[:n]

    return df


def create_random_walk_example(
    n_days: int,
    token1_price_initial: float,
    bias: float,
    variance: float,
    reward_token_price_initial: Optional[float] = None,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """
    Creates a random walk for token1 and optionally reward_token with a
    defined origin, bias, and variance. token0 remains "stable" at $1.0
    Note: bias and variance are per step. Since it is a random walk, each run gives
        different outputs.
    """
    df = initialize_price_dataframe(n_days, 1.0, token1_price_initial)

    # Apply the price change
    df["token1_price"] = random_walk(
        n_days, token1_price_initial, bias, variance, seed=seed
    )

    # Apply the price change
    if reward_token_price_initial:
        seed2 = None
        if seed:
            seed2 = int(
                seed * 2
            )  # Arbitrary deterministic, but separate, seed for rewards
        df["reward_token_price"] = random_walk(
            n_days, reward_token_price_initial, bias, variance, seed=seed2
        )

    return df


def create_history_from_files(
    coindix_pair: str,
    coindix_protocol: str,
    chain: str,
    token0_cream_name: str,
    token1_cream_name: str,
    token1_coingecko_id: str,
    reward_token_coingecko_id: Optional[str] = None,
    coindix_file: str = DEFAULT_COINDIX_HISTORY_FILE,
    cream_file: str = DEFAULT_CREAM_HISTORY_FILE,
    reward_apy_ratio: Optional[float] = None,
):
    """
    This is a scenario generator that extracts real pool APY data, borrow APY data,
    and prices from various sources. It then cleans them up and merges them by date
    in a format that is compatible with the simulator.

    * Pool APY data is derived a CoinDix history file, saved using this function:
        https://github.com/ClaudeF4491/crypto_data_fetchers/blob/b03f6655e8fc4baaba6b49c6ae38a700bc701cb2/adapters/apis/coindix.py#L197
    * Borrow APY data is derived from a Cream Finance history file, saved using this script:
        https://github.com/ClaudeF4491/crypto_data_fetchers/blob/main/scripts/download_history_cream.py
    * Price Data is derived from an API call to CoinGecko, via the get_coingecko_price_history() function in this notebook.

    Example Usage:

    df = create_history_from_files(
        "USDC.e-AVAX",
        "trader joe",
        "avalanche",
        "USDC.e",
        "WAVAX",
        "avalanche",
        "joe",
        coindix_file="coindix_vault_history_20220601.json",
        cream_file="cream_finance_history_20220601.json"
    )

    """  # NOQA

    """ Fetch CoinDix Pool APY History """
    df_coindix = extract_coindix_apy_history_from_file(
        coindix_file, chain, coindix_protocol, coindix_pair
    )
    apy_reward = df_coindix["reward"]
    apy_trading_fee = df_coindix["apy"]
    if (
        pd.isna(df_coindix["reward"]).all()
        or (df_coindix["reward"].max() <= 0)
        and reward_apy_ratio is not None
    ):
        print(
            f"No rewards found for this CoinDix pair. Setting reward based on "
            f"reward_apy_ratio={reward_apy_ratio}"
        )
        # No rewards found. Assume one based on reward_apy_ratio
        apy_reward = df_coindix["apy"] * reward_apy_ratio
        apy_trading_fee = df_coindix["apy"] * (1.0 - reward_apy_ratio)
    df_coindix["apy_trading_fee"] = apy_trading_fee
    df_coindix["apy_reward"] = apy_reward
    df_coindix = df_coindix[["date", "apy_trading_fee", "apy_reward"]]

    # Fill nans
    df_coindix = df_coindix.fillna(0.0)

    # Set index
    df_coindix = df_coindix.set_index("date", drop=True)

    """
    Fetch Borrow APYs from CREAM History File
    """
    df_borrows = extract_cream_borrow_apy_history_from_file(
        cream_file, chain, (token0_cream_name, token1_cream_name)
    )

    # Map naming
    rep = dict()
    for i, c in enumerate(df_borrows.columns):
        rep[c] = f"apy_borrow_token{i}"
    df_borrows = df_borrows.rename(rep, axis=1)

    """
    Merge the two, keeping only dates that are in both
    """
    df = df_coindix.join(df_borrows, how="inner")

    """
    Fetch token1 price data from CoinGecko
    """
    df_price = create_coingecko_price_history(
        token1_coingecko_id,
        start_time=int(df.index[0].timestamp()),
        end_time=int(
            df.index[-1].timestamp() + 60 * 60 * 24
        ),  # add one day for good measure
    )
    df_price["date"] = pd.to_datetime(df_price["date"], utc=True)
    df_price = df_price.set_index("date", drop=True)

    """
    Merge with token1 from coingecko
    """
    df = df.join(df_price, how="inner")

    """
    Optionally fetch reward token prices and merge
    """
    if reward_token_coingecko_id:
        df_reward = create_coingecko_price_history(
            reward_token_coingecko_id,
            start_time=int(df.index[0].timestamp()),
            end_time=int(
                df.index[-1].timestamp() + 60 * 60 * 24
            ),  # add one day for good measure
        )
        df_reward["date"] = pd.to_datetime(df_reward["date"], utc=True)
        df_reward = df_reward.set_index("date", drop=True)
        df_reward = df_reward.rename({"token1_price": "reward_token_price"}, axis=1)
        df_reward = df_reward[["reward_token_price"]]

        # Merge
        df = df.join(df_reward, how="inner")

    return df
