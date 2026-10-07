"""Payment run date and expected payout (policy §1.3, CLAUDE.md §8)."""
from datetime import date

from ..schemas import ExpectedPayout, SettlementSummary
from .config import PAYMENT_RUN_DAYS


def next_payment_run(d: date) -> date:
    """First 10th or 25th on or after d, rolling into the next month / year (§1.3)."""
    for day in PAYMENT_RUN_DAYS:
        if d.day <= day:
            return d.replace(day=day)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, PAYMENT_RUN_DAYS[0])


def expected_payout(summary: SettlementSummary, today: date, verified: bool,
                    scheduled_run: date | None = None) -> ExpectedPayout | None:
    """What the employee sees: payout if payable > 0, else recovery if recoverable > 0."""
    run = scheduled_run or next_payment_run(today)
    if summary.payable_paise > 0:
        return ExpectedPayout(amount_paise=summary.payable_paise, run_date=run,
                              estimated=not verified, kind="payout")
    if summary.recoverable_paise > 0:  # §1.3: deducted in the next payroll cycle
        return ExpectedPayout(amount_paise=summary.recoverable_paise, run_date=run,
                              estimated=not verified, kind="recovery")
    return None
