"""
Code to fetch or process data from external interfaces
"""
import json
import pandas as pd
from pycoingecko import CoinGeckoAPI
import requests
import time
from typing import Optional


def get_coingecko_price_history(
    coin_id: str, days: str = "max", interval: str = "daily"
) -> pd.Series:
    """
    Fetches daily prices for a coingecko ID.
    To get coingecko ID, look for "API id" on the CoinGecko page for that coin

    Returns a Seriees indexed on date and price in dollars as the field.
    """
    cg = CoinGeckoAPI()
    p = cg.get_coin_market_chart_by_id(
        coin_id, vs_currency="usd", days=days, interval=interval
    )
    df = pd.DataFrame(p["prices"], columns=["date", "price"])
    df["date"] = pd.to_datetime(df["date"] / 1000, utc=True, unit="s")
    df = df.set_index("date", drop=True)

    # Remove most recent since it is current moment
    df = df.iloc[:-1, :]

    # Convert to a series
    s = df["price"]
    s = s.tz_localize(None)

    return s


def extract_cream_borrow_apy_history_from_file(
    filename: str, comptroller: str, symbols: str
) -> pd.DataFrame():
    """
    Example:
    df_borrows = extract_cream_borrow_apy_history_from_file(
        "cream_finance_history_20220511.json",
        "avalanche",
        ("USDC.e", "WAVAX")
    )
    Or alternately replace first argument with the data object read in.
    """

    if not isinstance(filename, str):
        # Data passed in, not file
        data = filename
    else:
        with open(filename, "r") as f:
            data = json.load(f)

    dfs = []
    for sym in symbols:
        for dd in data:
            if (
                dd[0]["underlying_symbol"] == sym
                and dd[0]["comptroller"].lower() == comptroller
            ):
                break
        df_temp = pd.DataFrame(dd)[["date", "borrow_apy"]]
        df_temp["borrow_apy"] = (
            df_temp["borrow_apy"].astype(float) / 100.0
        )  # Cast to float and map to unit 1.0
        df_temp["date"] = pd.to_datetime(df_temp["date"], utc=True)
        df_temp = df_temp.rename({"borrow_apy": f"apy_borrow_{sym}"}, axis=1)
        dfs.append(df_temp)

    # Combine the two
    df_borrows = pd.merge(dfs[0], dfs[1], on="date", how="inner")
    df_borrows = df_borrows.sort_values("date", ascending=True).set_index(
        "date", drop=True
    )

    return df_borrows


def extract_coindix_apy_history_from_file(
    filename: str, chain: str, protocol: str, pair: str
) -> pd.DataFrame():
    """
    Example:
    df_coindix = extract_coindix_apy_history_from_file(
        "coindix_vault_history_20220511.json",
        "avalanche",
        "trader joe",
        "USDC.e-AVAX"
    )
    """
    # Load and configure top-level columns
    df = pd.read_json(filename)
    df["chain"] = df["chain"].str.lower()
    df["protocol"] = df["protocol"].str.lower()

    # Filter to pair/protocol of interest
    dft = df[
        (df["name"] == pair) & (df["protocol"] == protocol) & (df["chain"] == chain)
    ].iloc[0]["series"]
    dft = pd.DataFrame(dft)

    # Transform the columns
    for c in dft.columns:
        if c == "date":
            dft[c] = pd.to_datetime(dft[c], utc=True)
        else:
            dft[c] = dft[c].astype(
                float
            )  # Cast to float. Comes in mapped such that 0.1 is 10%

    return dft


def get_binance_klines(
    symbol: str, candle_size: str, start_time: int, end_time: int, limit: int
):
    """
    Gets candlesticks from Binance and returns as dataframe.

    Args:
        symbol: String representation of pair to fetch
        candle_size: See Binance API. e.g. 1h, 1d ...
        start_time: Start time in epoch seconds
        end_time: end time in epoch seconds
        limit: Limit to number of datapoints to fetch
    """

    BINANCE_KLINES_URL = "https://www.binance.com/api/v3/klines"

    params = dict(
        interval=candle_size,
        symbol=symbol,
        startTime=int(start_time * 1000),
        endTime=int(end_time * 1000),
        limit=limit,
    )
    resp = requests.get(BINANCE_KLINES_URL, params=params)
    resp_json = resp.json()
    df = pd.DataFrame(resp_json)
    df = df.iloc[:, 0:6]
    df = df.rename(
        {
            0: "Time",
            1: "Open",
            2: "High",
            3: "Low",
            4: "Close",
            5: "Volume",
        },
        axis="columns",
    )
    df["Time"] = df["Time"].astype(int) / 1e3
    df = df.sort_values("Time", ascending=True).reset_index(drop=True)
    df["Time"] = pd.to_datetime(df["Time"], unit="s")
    for c in df.columns:
        if c != "Time":
            df[c] = df[c].astype(float)
    return df


def create_coingecko_price_history(
    coin_id: str, start_time: Optional[int] = None, end_time: Optional[int] = None
) -> pd.DataFrame:
    """
    Fetches a symbol's price history from CoinGecko API.
    See get_coingecko_price_history for example.
    Converts to this format.
    Note: Currently assumes a stable is the base token.
    """
    if start_time is None:
        start_time = 0
    if end_time is None:
        end_time = int(time.time())
    s = get_coingecko_price_history(coin_id)

    # Filter by times
    start_ts = pd.Timestamp(start_time, unit="s")
    end_ts = pd.Timestamp(end_time, unit="s")
    s = s[start_ts:end_ts]

    # Pull out close events
    df = pd.DataFrame(s)
    df = df.rename({"price": "token1_price"}, axis=1)
    df["token0_price"] = 1.0
    df = df.reset_index()
    df = df.sort_values("date", ascending=True)
    df = df[["date", "token0_price", "token1_price"]]
    return df


def create_binance_price_history(
    symbol: str,
    candle_size: str = "1d",
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> pd.DataFrame:
    """
    Fetches a pair's history from Binance candlestick API.
    See get_binance_klines for example.
    Converts to this format.
    Note: Currently assumes a stable is the base token.
    """
    if start_time is None:
        start_time = 0
    if end_time is None:
        end_time = int(time.time())
    df_c = get_binance_klines(symbol, candle_size, start_time, end_time, 10000)

    # Pull out close events
    df = df_c[["Time", "Close"]]
    df = df.rename({"Time": "date", "Close": "token1_price"}, axis=1)
    df["token0_price"] = 1.0
    df = df[["date", "token0_price", "token1_price"]]
    return df
