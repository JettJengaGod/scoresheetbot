import math
from dataclasses import dataclass
from typing import Tuple



@dataclass
class EloPlayer:
    member_id: int = 0
    rating: int = 1500
    k: int = 50


def _probability(rating1, rating2):
    return 1.0 * 1.0 / (1 + 1.0 * math.pow(10, 1.0 * (rating1 - rating2) / 400))


def rating_update(p1: EloPlayer, p2: EloPlayer, result: int) -> Tuple[int, int]:
    prob_2 = _probability(p1.rating, p2.rating)
    prob_1 = _probability(p2.rating, p1.rating)

    # Case when Player 1 wins
    # return the Elo Ratings
    if result:
        p1_change = math.ceil(p1.k * (1 - prob_1))
        p2_change = math.floor(p2.k * (0 - prob_2))

    # Case when Player 2 wins
    # return the Elo Ratings
    else:
        p1_change = math.floor(p1.k * (0 - prob_1))
        p2_change = math.ceil(p2.k * (1 - prob_2))
    return p1_change, p2_change



