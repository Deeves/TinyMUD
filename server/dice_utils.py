from __future__ import annotations

"""
Dice utilities for common TTRPG notations.

Supported, composable features:
- Arithmetic of terms joined by + or - (e.g., 2d6 + 1d4 + 3)
- Basic dice: NdM, dM (count defaults to 1), d% (percentile, i.e., d100)
- Fate dice: NdF (each die is -1, 0, or +1)
- Keep/Drop: khN, klN, dhN, dlN (e.g., 4d6kh3)
- Advantage/Disadvantage: adv / dis (maps d20 to 2d20kh1 / 2d20kl1)
- Exploding dice: ! or !T (explode on max by default; or on >= T)
- Reroll low: rN (reroll once any initial die result <= N; common r1)

Notes and constraints:
- Keep/Drop applies after rerolls/explosions are resolved for each die.
- Explosions are compound (exploded dice can explode again).
- Advantage/Disadvantage is only auto-expanded when the die is a d20 and count <= 1.
- Expression may combine multiple terms: "2d6+1d4+2" or "1d20adv+3".

Examples:
- 1d20, 3d6, 1d100, 4d6kh3, 1d20adv, 1d20dis, 1d6!, 1d10!8, 5d6r1

"""

from dataclasses import dataclass, field
import re
import random
from typing import List, Optional, Tuple


@dataclass
class TermDetail:
    expr: str
    count: int
    sides: Optional[int]  # None for constants; -1 for Fate (dF)
    constant: int = 0
    rolls: List[int] = field(default_factory=list)
    exploded_from: List[List[int]] = field(default_factory=list)  # parallel to rolls: each list holds explosions
    kept: List[int] = field(default_factory=list)
    dropped: List[int] = field(default_factory=list)
    subtotal: int = 0
    note: str = ""


@dataclass
class RollResult:
    expression: str
    total: int
    terms: List[TermDetail]

    def __str__(self) -> str:
        parts: List[str] = []
        for t in self.terms:
            if t.sides is None:  # constant
                parts.append(f"{t.constant}")
                continue
            if t.sides == -1:
                base = f"{t.count}dF"
            elif t.sides == 100:
                base = f"{t.count}d%"
            else:
                base = f"{t.count}d{t.sides}"
            detail = base
            if t.rolls:
                rparts = []
                for i, r in enumerate(t.rolls):
                    exp = t.exploded_from[i] if i < len(t.exploded_from) else []
                    if exp:
                        rparts.append(f"{r}+{'+'.join(map(str, exp))}")
                    else:
                        rparts.append(str(r))
                detail += f" [{', '.join(rparts)}]"
            if t.kept or t.dropped:
                if t.kept:
                    detail += f" kept={t.kept}"
                if t.dropped:
                    detail += f" dropped={t.dropped}"
            if t.note:
                detail += f" ({t.note})"
            detail += f" => {t.subtotal}"
            parts.append(detail)
        joined = " + ".join(parts)
        return f"{self.expression} = {self.total} :: {joined}"


class DiceParseError(ValueError):
    pass


_WS = re.compile(r"\s+")

# Matches one term which can be a dice roll or a plain integer constant.
# Captures:
#  1: sign ('+' or '-') optional, defaults '+'
#  2: dice count (optional)
#  3: 'd' and sides, where sides can be an int, '%' or 'F'; if missing, it's a constant term
#  4: sides literal (int|%|F) if dice present
#  5: modifiers suffix (e.g., 'kh3! r1 adv')
_TERM_RE = re.compile(
    r"(?P<sign>[+-])?\s*(?:"
    r"(?:(?P<count>\d*)d(?P<sides>%|F|\d+)(?P<mods>(?:[a-zA-Z!<>]=?|\d|\s)+)?)"  # dice term
    r"|(?P<const>\d+))"  # or constant
)


def roll(expression: str, rng: Optional[random.Random] = None) -> RollResult:
    """Roll a dice expression and return structured results.

    expression examples:
      - '1d20', '3d6', '1d100', 'd%', '4d6kh3', '1d20adv+5', '2d6+1d4+2', '1d6!', '1d10!8', '5d6r1'
    """
    if rng is None:
        rng = random.Random()

    expr = expression.strip()
    if not expr:
        raise DiceParseError("Empty expression")

    # Normalize whitespace and ensure leading sign so parsing is consistent
    expr_norm = _WS.sub(" ", expr)
    if not expr_norm[0] in "+-":
        expr_norm = "+" + expr_norm

    idx = 0
    terms: List[TermDetail] = []
    total = 0

    for m in _TERM_RE.finditer(expr_norm):
        sign = -1 if (m.group('sign') == '-') else 1
        const = m.group('const')
        if const is not None:
            val = int(const) * sign
            t = TermDetail(expr=const, count=0, sides=None, constant=val, subtotal=val)
            terms.append(t)
            total += val
            continue

        count_s = m.group('count') or '1'
        sides_s = m.group('sides')
        mods = (m.group('mods') or '').strip()

        count = int(count_s) if count_s else 1
        if sides_s == '%':
            sides = 100
        elif sides_s == 'F':
            sides = -1  # Fate (dF)
        else:
            sides = int(sides_s)
            if sides < 1:
                raise DiceParseError("Die sides must be >= 1")

        # Parse modifiers: kh/kl/dh/dl, adv/dis, ![T], rN
        keep_type: Optional[str] = None  # 'kh', 'kl', 'dh', 'dl'
        keep_n: Optional[int] = None
        explode_threshold: Optional[int] = None
        reroll_leq: Optional[int] = None
        adv = False
        dis = False

        # Tokenize mods by whitespace boundaries
        for tok in mods.split():
            tok = tok.strip()
            if not tok:
                continue
            low = tok.lower()
            # keep/drop
            if low.startswith('kh') or low.startswith('kl') or low.startswith('dh') or low.startswith('dl'):
                mode = low[:2]
                num_s = low[2:] or '1'
                try:
                    num = int(num_s)
                except Exception:
                    raise DiceParseError(f"Invalid keep/drop number in '{tok}'")
                keep_type = mode
                keep_n = max(0, num)
                continue
            # advantage/disadvantage
            if low == 'adv':
                adv = True
                continue
            if low == 'dis':
                dis = True
                continue
            # explode: '!' or '!N' (explode on >= N)
            if low.startswith('!'):
                thr = low[1:]
                if thr:
                    try:
                        explode_threshold = int(thr)
                    except Exception:
                        raise DiceParseError(f"Invalid explosion threshold in '{tok}'")
                else:
                    explode_threshold = None  # will be resolved to 'max' below
                continue
            # reroll low: rN
            if low.startswith('r') and len(low) > 1:
                try:
                    reroll_leq = int(low[1:])
                except Exception:
                    raise DiceParseError(f"Invalid reroll threshold in '{tok}'")
                continue
            # Ignore unknown soft modifiers to stay permissive

        # Expand adv/dis for d20 if applicable
        if sides == 20 and count <= 1 and (adv or dis):
            count = 2
            if adv and dis:
                # cancels out; do nothing special
                pass
            elif adv:
                keep_type, keep_n = 'kh', 1
            elif dis:
                keep_type, keep_n = 'kl', 1

        # Execute rolls
        tdetail = TermDetail(expr=f"{count}d{'%' if sides==100 else ('F' if sides==-1 else sides)}{(' '+mods) if mods else ''}", count=count, sides=sides)

        if sides == -1:  # Fate dice: values -1, 0, +1
            for _ in range(count):
                v = rng.choice([-1, 0, +1])
                tdetail.rolls.append(v)
                tdetail.exploded_from.append([])
        else:
            def _roll_one() -> int:
                # 1..sides inclusive
                return rng.randint(1, sides)

            for _ in range(count):
                r = _roll_one()
                # reroll once if <= threshold (on the initial value only)
                if reroll_leq is not None and r <= reroll_leq:
                    r = _roll_one()
                tdetail.rolls.append(r)
                # explosions
                exps: List[int] = []
                # Determine threshold: default is max face
                thr = explode_threshold if explode_threshold is not None else sides
                if thr is not None:
                    current = r
                    while current >= thr:
                        current = _roll_one()
                        exps.append(current)
                        # continue exploding if new value also meets threshold
                tdetail.exploded_from.append(exps)

        # Determine kept vs dropped
        flat_totals: List[Tuple[int, int]] = []  # (value including explosions, original_index)
        for i, base in enumerate(tdetail.rolls):
            ex_sum = sum(tdetail.exploded_from[i]) if i < len(tdetail.exploded_from) else 0
            flat_totals.append((base + ex_sum, i))

        kept_idx: set[int] = set(range(len(flat_totals)))
        if keep_type and keep_n is not None and keep_n >= 0 and len(flat_totals) > 0:
            # Sort by value ascending
            sorted_pairs = sorted(flat_totals, key=lambda p: p[0])
            if keep_type == 'kh':
                keep_pairs = sorted_pairs[-keep_n:] if keep_n > 0 else []
            elif keep_type == 'kl':
                keep_pairs = sorted_pairs[:keep_n] if keep_n > 0 else []
            elif keep_type == 'dh':
                drop_pairs = sorted_pairs[-keep_n:] if keep_n > 0 else []
                keep_pairs = [p for p in sorted_pairs if p not in drop_pairs]
            elif keep_type == 'dl':
                drop_pairs = sorted_pairs[:keep_n] if keep_n > 0 else []
                keep_pairs = [p for p in sorted_pairs if p not in drop_pairs]
            else:
                keep_pairs = sorted_pairs
            kept_idx = {i for _, i in keep_pairs}

        # Build kept/dropped lists and subtotal
        subtotal = 0
        for i, (val, _) in enumerate(flat_totals):
            if i in kept_idx:
                tdetail.kept.append(val)
                subtotal += val
            else:
                tdetail.dropped.append(val)
        # Apply sign to subtotal
        subtotal *= sign
        tdetail.subtotal = subtotal
        if sign < 0 and tdetail.sides is not None:
            tdetail.note = 'negated'

        total += subtotal
        terms.append(tdetail)

    if not terms:
        raise DiceParseError("No terms parsed from expression")

    return RollResult(expression=expr, total=total, terms=terms)


def roll_simple(expr: str) -> int:
    """Convenience wrapper returning only the final total."""
    return roll(expr).total


if __name__ == "__main__":
    demo = [
        "1d20", "3d6", "1d100", "2d20kh1", "1d20adv", "1d20dis", "4d6kh3", "5d6r1", "1d6!", "1d10!8", "4dF", "2d6+1d4+2",
    ]
    rng = random.Random(42)
    for e in demo:
        print(roll(e, rng=rng))
