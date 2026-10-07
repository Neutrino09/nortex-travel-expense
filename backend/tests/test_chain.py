"""Every row of the §6 expected-chains table."""
import pytest
from sqlmodel import select

from app.models import Employee
from app.policy.chain import build_chain

SURESH, MEERA, ARVIND, NANDITA = "NX-2210", "NX-1108", "NX-1002", "NX-1000"
RAVI, KAVITHA, CHAITANYA = "NX-3305", "NX-3300", "NX-4471"


@pytest.fixture()
def emps(session):
    return {e.emp_code: e for e in session.exec(select(Employee))}


def codes(chain):
    return [s.approver_code for s in chain]


def chain(emps, who, rupees, international=False, force_hod=False, finance=True):
    return build_chain(emps[who], rupees * 100, international, force_hod, finance, emps)


def test_settlement_26388(emps):
    c = build_chain(emps[CHAITANYA], 2_638_844, False, False, True, emps)
    assert codes(c) == [SURESH, MEERA, RAVI]


def test_settlement_24133(emps):
    c = build_chain(emps[CHAITANYA], 2_413_344, False, False, True, emps)
    assert codes(c) == [SURESH, RAVI]


def test_settlement_80000(emps):
    assert codes(chain(emps, CHAITANYA, 80_000)) == [SURESH, MEERA, ARVIND, RAVI]


def test_international(emps):
    assert codes(chain(emps, CHAITANYA, 10_000, international=True)) == [SURESH, MEERA, ARVIND, NANDITA, RAVI]


def test_entertainment_forces_hod(emps):
    assert codes(chain(emps, CHAITANYA, 20_000, force_hod=True)) == [SURESH, MEERA, RAVI]


def test_suresh_rm_and_hod_collapse(emps):
    c = chain(emps, "NX-2210", 30_000)
    assert codes(c) == [MEERA, RAVI]


def test_ravi_escalates_hod_to_head_of_division(emps):
    c = chain(emps, RAVI, 30_000)
    assert codes(c) == [KAVITHA, ARVIND, KAVITHA]
    assert [s.level for s in c] == ["RM", "HOD", "FINANCE"]
    assert "escalated" in c[1].note


def test_nandita_only_finance(emps):
    c = chain(emps, NANDITA, 5_000)
    assert codes(c) == [RAVI]
    assert c[0].note  # records that the RM level was skipped


def test_request_has_no_finance_step(emps):
    assert codes(chain(emps, CHAITANYA, 43_500, finance=False)) == [SURESH, MEERA]


def test_claimant_never_in_own_chain(emps):
    for who in emps:
        assert who not in codes(chain(emps, who, 500_000, international=True, finance=False))
