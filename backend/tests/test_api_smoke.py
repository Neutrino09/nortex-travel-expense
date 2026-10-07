"""Full happy path from CLAUDE.md §9 over HTTP, switching users through /auth/login."""
SID = 1  # the seeded draft settlement for TRQ-2026-0001


def test_full_flow_over_http(login_as):
    chaitanya, suresh, meera, ravi = (login_as(c) for c in ("NX-4471", "NX-2210", "NX-1108", "NX-3305"))

    # Employee imports the sample inbox; the dinner blocks submission until attendees are added.
    r = chaitanya.post(f"/api/settlements/{SID}/import-sample")
    assert r.status_code == 200, r.text
    assert r.json()["new_documents"] == 17
    assert chaitanya.post(f"/api/settlements/{SID}/import-sample").json()["new_documents"] == 0  # idempotent

    v = chaitanya.post(f"/api/settlements/{SID}/validate").json()
    assert v["summary"]["net_paise"] == 2_638_844
    assert v["summary"]["payable_paise"] == 638_844
    assert [s["approver_code"] for s in v["chain_preview"]] == ["NX-2210", "NX-1108", "NX-3305"]
    assert any(f["severity"] == "BLOCK" and f["rule_id"] == "R-ENT-ATT" for f in v["findings"])
    assert chaitanya.post(f"/api/settlements/{SID}/submit").status_code == 400

    # Add attendees to the entertainment line, then submit.
    s = chaitanya.get(f"/api/settlements/{SID}").json()
    ent = next(line for line in s["lines"] if line["head"] == "business_entertainment")
    att = [{"name": f"Guest {i}", "organisation": "Vertex Technologies"} for i in range(1, 5)]
    assert chaitanya.patch(f"/api/settlements/{SID}/lines/{ent['id']}", json={"attendees": att}).status_code == 200
    assert chaitanya.post(f"/api/settlements/{SID}/submit").status_code == 200

    # Out-of-turn approver and self-approval are refused.
    assert meera.post(f"/api/approvals/settlement/{SID}/act", json={"action": "approve"}).status_code == 403
    assert chaitanya.post(f"/api/approvals/settlement/{SID}/act", json={"action": "approve"}).status_code == 403

    assert [i["entity_id"] for i in suresh.get("/api/approvals/inbox").json()] == [str(SID)]
    for who in (suresh, meera, ravi):
        r = who.post(f"/api/approvals/settlement/{SID}/act", json={"action": "approve"})
        assert r.status_code == 200, r.text
    assert r.json()["status"] == "verified"

    # Payout of ₹6,388.44 on the next run after APP_TODAY (22 Jun 2026) -> 25 Jun 2026.
    s = chaitanya.get(f"/api/settlements/{SID}").json()
    pay = s["payments"][0]
    assert (pay["kind"], pay["amount_paise"], pay["run_date"]) == ("payout", 638_844, "2026-06-25")
    assert ravi.post(f"/api/finance/payments/{pay['id']}/mark-paid").status_code == 200
    assert chaitanya.get(f"/api/settlements/{SID}").json()["status"] == "paid"
    assert chaitanya.get("/api/requests/TRQ-2026-0001").json()["stage"]["step_index"] == 5
