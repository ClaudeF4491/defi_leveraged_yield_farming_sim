"""
Various support functions
"""
import numpy as np
from typing import Optional, Sequence


def iloss_amt(k: float, r: float) -> Sequence[float]:
    """
    NB: This wasn't in video screenshot, so derived it manually.

    Calculate impermanent loss given constant product formula: x*y = k.
    Ref: https://jamesbachini.com/impermanent-loss/

    Given x*y = k

    x_new = sqrt(k / r)
    y_new = sqrt(k * r)

    Assumes price ratio is price_b / price_a

    Args:
        k: lp constant
        x: price ratio

    Returns:
        iloss_value: Values after impermanent loss calculated,
            where first element is # of tokens remaining in pool A
            and second element is # tokens in pool B
    """
    iloss_val = []
    print
    x = (k * r) ** 0.5
    y = (k / r) ** 0.5
    iloss_val = [x, y]
    return iloss_val


def random_walk(
    n: int, origin: float, bias: float, variance: float, seed: Optional[int] = None
) -> np.array:
    """
    Generates n-length array from random walk with bias and variance per step.
    Optionally set seed for deterministic results.
    """
    # Set randon number generator just for this function
    rng = np.random.RandomState(seed)
    r = (
        rng.normal(
            bias,
            np.sqrt(variance),
            n,
        )
        + 1.0
    )
    walk = np.cumprod(r) * origin
    walk = np.insert(walk, 0, origin)[:-1]
    return walk
