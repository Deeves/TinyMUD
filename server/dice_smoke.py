from dice_utils import roll
import random

if __name__ == "__main__":
    rng = random.Random(1)
    tests = [
        '1d20', '3d6', '1d100', 'd%', '4d6kh3', '1d20adv+5', '2d6+1d4+2', '1d6!', '1d10!8', '5d6r1', '4dF'
    ]
    for e in tests:
        print(roll(e, rng=rng))
