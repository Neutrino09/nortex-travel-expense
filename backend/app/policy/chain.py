"""Approval chain builder (policy §2, CLAUDE.md §6). Pure function over the employee dict."""
from dataclasses import dataclass

from ..models import Employee
from ..schemas import ChainStepOut
from .config import (FINANCE_APPROVER, FINANCE_APPROVER_ALT, HOD_ABOVE_PAISE, HODIV_ABOVE_PAISE,
                     LEVEL_ORDER, LEVEL_ROLE, MD_ABOVE_PAISE, ROLE_RANK)


@dataclass
class StepSpec:
    level: str
    approver_code: str
    note: str | None = None


def required_levels(value_paise: int, international: bool, force_hod: bool) -> list[str]:
    """Levels are cumulative: a higher tier brings every level below it (§2)."""
    top = 1  # RM always
    if value_paise > HOD_ABOVE_PAISE:
        top = 2
    if value_paise > HODIV_ABOVE_PAISE:
        top = 3
    if value_paise > MD_ABOVE_PAISE or international:
        top = 4
    if force_hod:  # §3.5 entertainment above ₹2,000
        top = max(top, 2)
    return LEVEL_ORDER[:top]


def ancestors_of(claimant: Employee, employees: dict[str, Employee]) -> list[Employee]:
    """Reporting line upwards. The claimant never appears (§2.2)."""
    line, seen, code = [], {claimant.emp_code}, claimant.reporting_manager_code
    while code and code in employees and code not in seen:
        seen.add(code)
        line.append(employees[code])
        code = employees[code].reporting_manager_code
    return line


def _pick_for_level(level: str, ancestors: list[Employee]) -> tuple[Employee | None, str | None]:
    """RM = direct manager; others = first ancestor with that role, else escalate (§2)."""
    if level == "RM":
        return (ancestors[0], None) if ancestors else (None, "No reporting manager — level skipped")
    role = LEVEL_ROLE[level]
    for a in ancestors:
        if a.role == role:
            return a, None
    for a in ancestors:  # escalate to the first ancestor holding a higher role
        if ROLE_RANK.get(a.role, 0) > ROLE_RANK[role]:
            return a, f"No {role} above claimant — escalated to {a.role}"
    return None, f"No {role} above claimant — level skipped"


def _collapse(specs: list[StepSpec]) -> list[StepSpec]:
    """Consecutive duplicate approvers become one step; notes merge; the higher level wins."""
    out: list[StepSpec] = []
    for s in specs:
        if out and out[-1].approver_code == s.approver_code:
            notes = [n for n in (out[-1].note, s.note) if n]
            out[-1] = StepSpec(s.level, s.approver_code, "; ".join(notes) or None)
        else:
            out.append(s)
    return out


def build_chain(claimant: Employee, value_paise: int, international: bool, force_hod: bool,
                include_finance: bool, employees: dict[str, Employee]) -> list[StepSpec]:
    ancestors = ancestors_of(claimant, employees)
    specs: list[StepSpec] = []
    carry: str | None = None  # note from a skipped level, attached to the next step
    for level in required_levels(value_paise, international, force_hod):
        person, note = _pick_for_level(level, ancestors)
        if person is None:
            carry = "; ".join(n for n in (carry, note) if n)
            continue
        note = "; ".join(n for n in (carry, note) if n) or None
        carry = None
        specs.append(StepSpec(level, person.emp_code, note))
    specs = _collapse(specs)
    if include_finance:  # Finance after business approvals (§2.1)
        finance = FINANCE_APPROVER_ALT if claimant.emp_code == FINANCE_APPROVER else FINANCE_APPROVER
        specs.append(StepSpec("FINANCE", finance, carry))
    return _collapse(specs)


def to_out(specs: list[StepSpec], employees: dict[str, Employee]) -> list[ChainStepOut]:
    return [ChainStepOut(seq=i + 1, level=s.level, approver_code=s.approver_code,
                         approver_name=employees[s.approver_code].name, note=s.note)
            for i, s in enumerate(specs)]
