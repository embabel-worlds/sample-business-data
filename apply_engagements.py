"""Add the CRM's day-to-day history to the book: more people, the emails and calls sales logged,
and the follow-ups each owner has open. `to_book.py` runs it after `apply_arcs.py`.

The workbooks hold one contact per company and no correspondence, so a question a salesperson
asks every Monday has nothing to answer from: who have I gone quiet on, which deals have stalled,
what is overdue on my list. The rows are in `additions/`, drafted once and committed, so the book
stays deterministic; this script checks them against the book and writes

    crm/contacts.csv   the drafted people appended; owner and location come from their account
    crm/emails.csv     one row per logged email, `direction` outbound or inbound, `sent_at` UTC
    crm/calls.csv      one row per logged call, `outcome` connected, voicemail or no_answer
    crm/followups.csv  the drafted follow-ups appended; `status` open or done

and plants three signals a harness can count, each written to `arcs.csv`:

    gone quiet       per salesperson, exactly 6 contacts they have been in touch with whose
                     newest email, call or meeting is 30+ days old. Counting emails alone gives
                     the same 6, so either reading of "not emailed" is right.
    stalled deals    exactly 6 open deals, Globex 302 among them, with no email or call logged
                     on the deal in the last 45 days
    open follow-ups  per owner, exactly 5 open, 2 of them past due

"Engagement" means an email, a call or a meeting, which is what a CRM counts as contact; a
note is not. No newest engagement and no due date sits within MARGIN days of a cut-off, so a
loader that shifts the dates, or a time zone, cannot move a row across it. A harness that asks
days after seeding must count from its own today, not from the as-of date.

Every check runs before anything is written.
"""

import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from apply_arcs import CONTROLS, read, write

ADDITIONS = Path(__file__).parent / "additions"
SALES = ["Mike Davis", "Jenna Lopez", "Sophie Turner"]
OWNERS = SALES + ["Dana Whitfield"]
QUIET_DAYS, STALL_DAYS, MARGIN = 30, 45, 4
STALLED = {"302", "305", "311", "326", "335", "339"}
# The arcs' must-nots, as words that would break them if sales wrote them down.
FORBIDDEN = {"chumbucket.com": r"pay|invoice|card|billing", "northwind-traders.example": r"export"}


def day(text):
    return date.fromisoformat(text[:10])


def check_far(when, cut, what):
    assert abs((when - cut).days) > MARGIN, f"{what} on {when} is within {MARGIN} days of the cut-off {cut}"


def apply(root, as_of):
    as_of = date.fromisoformat(as_of)
    quiet_cut, stall_cut = as_of - timedelta(days=QUIET_DAYS), as_of - timedelta(days=STALL_DAYS)
    accounts = {a["account_key"]: a for a in read(root, "crm/accounts.csv")}
    deals = {o["source_id"]: o for o in read(root, "crm/opportunities.csv")}
    arcs = read(root, "arcs.csv")
    story = {k for a in arcs for k in a["account_key"].split(",")} - {"", "*"}
    # A follow-up is what makes trouble ACKNOWLEDGED, so one on a troubled account changes its answer.
    troubled = story | set(CONTROLS) \
        | {c["account_key"] for c in read(root, "support/cases.csv") if c["status"] == "open"} \
        | {i["account_key"] for i in read(root, "billing/invoices.csv") if i["status"] != "paid"}

    contacts = read(root, "crm/contacts.csv")
    first_id = max(int(c["source_id"]) for c in contacts) + 1
    for n, c in enumerate(read(ADDITIONS, "contacts.csv")):
        a = accounts[c["account_key"]]
        assert c["email"].endswith("@" + c["account_key"]), c["email"]
        contacts.append({**dict.fromkeys(contacts[0], ""), **c, "owner": a["owner"], "city": a["city"],
                         "region": a["region"], "country": a["country"], "source_id": str(first_id + n)})
    person = {c["email"]: c for c in contacts}
    assert len(person) == len(contacts), "duplicate contact email"
    assert 120 <= len(contacts) <= 140, f"{len(contacts)} contacts"
    per_account = Counter(c["account_key"] for c in contacts)
    thin = sorted({o["account_key"] for o in deals.values() if o["status"] == "open"} - {"writes-sandbox.example"}
                  - {k for k, n in per_account.items() if n >= 3})
    assert not thin, f"accounts with an open deal and fewer than 3 contacts: {thin}"

    emails, calls = read(ADDITIONS, "emails.csv"), read(ADDITIONS, "calls.csv")
    touches, deal_touches = defaultdict(list), defaultdict(list)
    for kind, rows, at in (("email", emails, "sent_at"), ("call", calls, "called_at")):
        assert len({r["source_id"] for r in rows}) == len(rows), f"duplicate {kind} source_id"
        for r in rows:
            who = person[r["contact_email"]]
            assert r["account_key"] == who["account_key"], f"{r['source_id']} account is not its contact's"
            assert r["account_key"] not in CONTROLS, f"{r['source_id']} touches a control account"
            assert r["owner"] in OWNERS and r["direction"] in ("outbound", "inbound"), r["source_id"]
            assert kind == "email" or r["outcome"] in ("connected", "voicemail", "no_answer"), r["source_id"]
            when = day(r[at])
            assert date(2026, 1, 1) <= when < as_of, f"{r['source_id']} dated {when}"
            text = " ".join(r[k] for k in ("subject", "title", "body") if k in r)
            pattern = FORBIDDEN.get(r["account_key"])
            assert not (pattern and re.search(pattern, text, re.I)), f"{r['source_id']} breaks an arc's must-not"
            touches[r["contact_email"]].append((when, kind))
            if r["opportunity_id"]:
                assert deals[r["opportunity_id"]]["account_key"] == r["account_key"], r["source_id"]
                deal_touches[r["opportunity_id"]].append(when)
    for m in read(root, "crm/meetings.csv"):
        if m["attendee_email"]:
            touches[m["attendee_email"]].append((day(m["starts_at"]), "meeting"))

    def quiet(kinds):
        newest = {e: max(w for w, k in ts if k in kinds) for e, ts in touches.items() if any(k in kinds for _, k in ts)}
        return {e for e, w in newest.items() if w <= quiet_cut}

    for e, ts in touches.items():
        check_far(max(w for w, _ in ts), quiet_cut, f"{e}'s newest engagement")
    gone_quiet = quiet({"email", "call", "meeting"})
    assert gone_quiet == quiet({"email"}), \
        f"emails alone give a different quiet set: {sorted(gone_quiet ^ quiet({'email'}))}"
    quiet_by_owner = {o: sorted(e for e in gone_quiet if person[e]["owner"] == o) for o in SALES}
    for o, es in quiet_by_owner.items():
        assert len(es) == 6, f"{o} has {len(es)} quiet contacts: {es}"

    open_deals = {i for i, o in deals.items() if o["status"] == "open"}
    for i in open_deals & set(deal_touches):
        check_far(max(deal_touches[i]), stall_cut, f"deal {i}'s newest engagement")
    stalled = {i for i in open_deals if not deal_touches[i] or max(deal_touches[i]) <= stall_cut}
    assert stalled == STALLED, f"stalled deals are {sorted(stalled)}, expected {sorted(STALLED)}"
    assert all(deal_touches[i] for i in STALLED), "a stalled deal needs an engagement to have gone quiet after"
    slipping = sorted(i for i in open_deals - stalled if day(deals[i]["close_on"]) < as_of)

    followups = read(root, "crm/followups.csv")
    for f in followups:
        f.update(status="open", completed_on="")
    for n, f in enumerate(read(ADDITIONS, "followups.csv"), len(followups) + 1):
        assert f["account_key"] in accounts and f["account_key"] not in troubled, \
            f"follow-up on {f['account_key']}, an arc or troubled account, would change its answer"
        followups.append({"source_id": f"followup-{n:04d}", **f})
    for f in followups:
        assert f["owner"] in OWNERS and f["status"] in ("open", "done"), f["source_id"]
        assert day(f["scheduled_on"]) <= day(f["due_on"]) and day(f["scheduled_on"]) < as_of, f["source_id"]
        assert (f["status"] == "done") == bool(f["completed_on"]), f["source_id"]
        if f["status"] == "open":
            check_far(day(f["due_on"]), as_of, f"{f['source_id']} due")
        else:
            assert day(f["completed_on"]) < as_of, f["source_id"]
    for o in OWNERS:
        mine = [f for f in followups if f["owner"] == o and f["status"] == "open"]
        late = [f for f in mine if day(f["due_on"]) < as_of]
        assert (len(mine), len(late)) == (5, 2), f"{o} has {len(mine)} open follow-ups, {len(late)} past due"

    for i in contacts:
        newest = max((w for w, _ in touches.get(i["email"], [])), default=None)
        if newest and newest.isoformat() > i["last_activity_on"]:
            i["last_activity_on"] = newest.isoformat()
    when = f"as of {as_of}"
    for o, es in quiet_by_owner.items():
        arcs.append({"arc": "gone quiet", "account_key": "*", "surfaces_as":
                     f"{o}: {', '.join(es)} - newest email, call or meeting {QUIET_DAYS}+ days before, {when}",
                     "must_not": "any contact never emailed; any contact engaged in the window"})
    arcs.append({"arc": "stalled deals", "account_key": "*", "surfaces_as":
                 f"open deals {', '.join(sorted(stalled))}: no email or call on the deal for {STALL_DAYS}+ days, {when}",
                 "must_not": "any other open deal"})
    arcs.append({"arc": "slipping but active", "account_key": "*", "surfaces_as":
                 f"open deals {', '.join(slipping)}: past their close date, engaged within {STALL_DAYS} days",
                 "must_not": "STALLED"})
    for o in OWNERS:
        late = sorted(f["source_id"] for f in followups
                      if f["owner"] == o and f["status"] == "open" and day(f["due_on"]) < as_of)
        arcs.append({"arc": "open follow-ups", "account_key": "*", "surfaces_as":
                     f"{o}: 5 open, past due {', '.join(late)}, {when}", "must_not": ""})

    return {"crm/contacts": write(root, "crm/contacts.csv", contacts),
            "crm/emails": write(root, "crm/emails.csv", emails),
            "crm/calls": write(root, "crm/calls.csv", calls),
            "crm/followups": write(root, "crm/followups.csv", followups),
            "arcs": write(root, "arcs.csv", arcs)}
