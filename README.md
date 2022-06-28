# defi_leveraged_yield_farming_sim
Time-Series simulator to assess performance of Leveraged Yield Farming (LYF) and Pseudo Delta Neutral (PDN) strategies in DeFi.
- See `farming_simulator.ipynb` for the simulation, details, and example usage.
- See `optimize_rebalance_threshold.ipynb` for an example of how to optimize a strategy parameter via exhaustive grid-search
  - It attempts to find the best rebalancing threshold for a 3X LYF PDN strategy on historical AVAX-USDC.e APY and price data.
