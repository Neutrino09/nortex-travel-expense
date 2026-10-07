"""§8 payment-run dates."""
from datetime import date

import pytest

from app.policy.payments import expected_payout, next_payment_run
from app.policy.rules import summarize


@pytest.mark.parametrize("d,expected", [
    (date(2026, 6, 9), date(2026, 6, 10)),
    (date(2026, 6, 10), date(2026, 6, 10)),
    (date(2026, 6, 11), date(2026, 6, 25)),
    (date(2026, 6, 25), date(2026, 6, 25)),
    (date(2026, 6, 26), date(2026, 7, 10)),
    (date(2026, 12, 26), date(2027, 1, 10)),
])
def test_next_payment_run(d, expected):
    assert next_payment_run(d) == expected


def test_expected_payout_is_estimated_until_verified():
    summary = summarize([], 0)
    assert expected_payout(summary, date(2026, 6, 22), False) is None
