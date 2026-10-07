# Demo script (3–5 minutes)

Start: `docker compose up --build`, open http://localhost:8001. `APP_TODAY=2026-06-22`.

1. **Login as Chaitanya (Employee).** *Say:* "No passwords, a log-in-as picker; every permission is checked on the server." Dashboard: TRQ-2026-0001 at *Trip settlement*. Point at the "Migrated from email — issues found" banner: the advance was over the 60% cap and HoD approval was missing; the app would have caught both.
2. **Open the settlement → Load sample inbox.** *Say:* "15 emails and 2 receipts, triaged in seconds. The model only extracts; Python decides." Walk the traps: duplicate Uber resend (excluded), failed payment, voucher vs invoice, Deepa's ride, the promo, company-paid flights (memo only), and the hotel folio split, with laundry and minibar disallowed rather than dropped.
3. **Summary card.** Net ₹26,388.44, payable ₹6,388.44, chain Suresh → Meera → Ravi. Submit is disabled: the dinner needs attendees. Add 4 attendees from Vertex Technologies; Submit enables. *Say:* "Blocking errors are impossible to submit."
4. **Switch to Suresh (Manager).** Inbox → open the claim → **Return** with a remark. Back to Chaitanya: see the remark, **Resubmit** (same TRQ ID, revision 2). Switch to Suresh: **Approve**. Switch to **Meera**: Approve (required because the claim is over ₹25k and the entertainment over ₹2k).
5. **Switch to Ravi (Admin/Finance).** Finance → Claims to verify → **Verify**. Payout ₹6,388.44 scheduled for **25 Jun 2026**. Payment runs → **Mark paid**.
6. **Back as Chaitanya.** Stepper shows Payout complete; the timeline shows every step. *Optional:* as **Imran**, start a new request with an advance above 60% and show the live block.

Close with: the principle, the offline-testable golden pack, and the limitations in NOTE.md.
