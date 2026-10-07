"""Money is ALWAYS integer paise. No floats anywhere in money maths."""
from decimal import ROUND_HALF_UP, Decimal


def rupees_to_paise(value) -> int:
    """Convert an extracted rupee amount (number or str) to paise, rounding half-up."""
    return int((Decimal(str(value)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def format_inr(paise: int) -> str:
    """26388.44 rupees -> '₹26,388.44' with Indian digit grouping (lakh/crore)."""
    sign = "-" if paise < 0 else ""
    rupees, ps = divmod(abs(paise), 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{sign}₹{s}.{ps:02d}"


def prorate(part_paise: int, whole_paise: int, amount_paise: int) -> int:
    """amount × part / whole, rounded half-up, in integers (e.g. tax on a disallowed item)."""
    if whole_paise == 0:
        return 0
    return (amount_paise * part_paise * 2 + whole_paise) // (whole_paise * 2)
