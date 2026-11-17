"""Add the CRM's day-to-day history to the book: more people, the emails and calls sales logged,
and the follow-ups each owner has open. `to_book.py` runs it after `apply_arcs.py`.

The workbooks hold one contact per company and no correspondence, so a question a salesperson
asks every Monday has nothing to answer from: who have I gone quiet on, which deals have stalled,
what is overdue on my list. The rows are in `additions/`, drafted once and committed, so the book
stays deterministic; this script checks them against the book and writes

    crm/contacts.csv       the drafted people appended, ids from 501; owner and location come from
                           their account, `last_activity_on` is their newest email, call or meeting
    crm/emails.csv         one row per logged email, `direction` outbound or inbound, `sent_at` UTC
    crm/calls.csv          one row per logged call, `outcome` connected, voicemail or no_answer
    crm/followups.csv      the drafted follow-ups appended; `status` open or done
    crm/opportunities.csv  stalled deals' close dates moved past the as-of date; `modified_on` at
                           least the deal's newest email or call

and plants these signals a harness can count, each written to `arcs.csv`:

    gone quiet       per salesperson, exactly 6 contacts with no email, call or meeting in the 30
                     days before as-of. Every other contact had an outbound email in the 25 days
                     before, so never-contacted people add nobody.
    not emailed      per salesperson, the same 6 plus one control: newest email 45+ days old, but
                     a connected call within 25 days. Telling it from "gone quiet" shows which
                     field a reader used.
    stalled deals    exactly 6 open deals with no email or call on the deal in the 45 days before
                     as-of. Their close dates lie after as-of, so they are not slipping.
    slipping deals   exactly 4 open deals whose close date has passed; each had an outbound email
                     or call on the deal within 45 days, so none is stalled.
    open follow-ups  per owner, exactly 5 open, 2 of them past due, none on an arc account

HubSpot's "last contacted" counts outbound email, calls and meetings, not inbound email. Every
signal above is asserted twice, counting inbound email and not, and gives the same answer.

"Engagement" means an email, a call or a meeting, which is what a CRM counts as contact; a
note is not. No newest engagement, close date or due date sits within MARGIN days of a cut-off,
so a loader that shifts the dates, or a time zone, cannot move a row across it. A harness that
asks days after seeding must count from its own today, not from the as-of date.

Every check runs before anything is written.
"""

import calendar
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from apply_arcs import CONTROLS, SANDBOX, read, write

ADDITIONS = Path(__file__).parent / "additions"
SALES = ["Mike Davis", "Jenna Lopez", "Sophie Turner"]
OWNERS = SALES + ["Dana Whitfield"]
QUIET_DAYS, RECENT_DAYS, OLD_EMAIL_DAYS, STALL_DAYS, MARGIN = 30, 25, 45, 45, 4
# Added contacts start here, clear of every other numeric id family (accounts 2xx, deals 3xx,
# cases 1xxx): Odoo keys contacts and companies alike as partners by `BOOK-<source_id>`.
FIRST_CONTACT_ID = 501
QUIET = {
    "Mike Davis": {"grace.t@nakatomi.com", "h.bailey@blue-sun.com", "i.sorensen@blue-sun.com",
                   "l.oconnor@dunder.ie", "noah.s@blackmesa.com", "r.singh@vandelay.com"},
    "Jenna Lopez": {"d.chen@globex.io", "j.reed@plumbus.com", "n.rivera@xyzcorp.com", "n.walker@buy-n-large.com",
                    "priya.patel@stark.com", "tom.harlow@wayfarer-travel.example"},
    "Sophie Turner": {"c.bucket@wonkachoco.com", "h.watson@bakerstreet.co.uk", "joan.h@sterling-cooper.com",
                      "l.hassan@wonkachoco.com", "mason.c@sterling-cooper.com",
                      "priya.raman@brightline-analytics.example"},
}
EMAIL_CONTROL = {"Mike Davis": "wendy.t@aperture-systems.com", "Jenna Lopez": "tyler.f@yoyodyne.com",
                 "Sophie Turner": "k.brennan@hyperion.com"}
STALLED = {"302", "305", "311", "326", "335", "339"}
SLIPPING = {"308", "322", "328", "346"}
# A stalled deal's close date is pushed out, so "past its close date" never finds one. Hooli 307
# and Hyperion 323 closed three days after as-of, too near the cut-off to survive a date shift.
CLOSE_ON = {"302": "2026-07-31", "305": "2026-07-15", "311": "2026-07-10", "326": "2026-08-14",
            "335": "2026-07-24", "339": "2026-08-28", "307": "2026-07-15", "323": "2026-07-31"}
TROUBLE = r"\b(issue|problem|bug|outage|overdue|late|fail\w*|escalat\w*|complain\w*|cancel\w*|refund\w*|disput\w*|unpaid)\b"
# The arcs' must-nots, as words that would break them if sales wrote them down. A control must say nothing.
FORBIDDEN = {"chumbucket.com": r"pay|invoice|card|billing", "northwind-traders.example": r"export",
             **{k: TROUBLE for k in CONTROLS}}
ANY, EMAIL = {"email", "call", "meeting"}, {"email"}
# A loader moves the dates inside texts as it moves the date fields: ISO, "June 16", "16 June".
MONTH = "|".join(sorted({n for m in calendar.month_name[1:] for n in (m, m[:3])} | {"Sept"}, key=len, reverse=True))
TEXT_DATE = re.compile(rf"(?:\b(?P<wd>{'|'.join(calendar.day_name)}),? )?(?:\b(?P<iso>\d{{4}}-\d\d-\d\d)\b"
                       rf"|\b(?P<m>{MONTH})\.? (?P<d>\d{{1,2}})(?:st|nd|rd|th)?\b"
                       rf"|\b(?P<d2>\d{{1,2}})(?:st|nd|rd|th)? (?P<m2>{MONTH})\b)")
# What it cannot move: a day without its month, or a numeric month/day.
DAY_ONLY = re.compile(r"\bthe \d{1,2}(?:st|nd|rd|th)\b|(?<![\d/])\d{1,2}/\d{1,2}(?![\d/])")


def day(text):
    return date.fromisoformat(text[:10])


def check_far(when, cut, what):
    assert abs((when - cut).days) > MARGIN, f"{what} on {when} is within {MARGIN} days of the cut-off {cut}"


def check_text_dates(tables, year):
    """Every date a text names is a real day, a weekday beside it is that day's, and none is a form a loader
    cannot move. A month-day without a year is read in `year`."""
    n = 0
    for name, rows in tables.items():
        for r in rows:
            for k, v in r.items():
                where = f"{name} {r.get('source_id') or r.get('email')} {k}"
                bad = isinstance(v, str) and DAY_ONLY.search(v)
                assert not bad, f"{where}: '{bad and bad[0]}' names a day a loader cannot move"
                for m in TEXT_DATE.finditer(v if isinstance(v, str) else ""):
                    month, d = (m["m"], m["d"]) if m["m"] else (m["m2"], m["d2"])
                    try:
                        when = date.fromisoformat(m["iso"]) if m["iso"] else \
                            date(year, next(i for i, f in enumerate(calendar.month_name) if i and f.startswith(month[:3])), int(d))
                    except ValueError:
                        raise AssertionError(f"{where}: '{m[0]}' is not a real date")
                    assert not m["wd"] or m["wd"] == calendar.day_name[when.weekday()], \
                        f"{where}: '{m[0]}' but {when} is a {calendar.day_name[when.weekday()]}"
                    n += 1
    return n


def apply(root, as_of):
    as_of = date.fromisoformat(as_of)
    quiet_cut, stall_cut = as_of - timedelta(days=QUIET_DAYS), as_of - timedelta(days=STALL_DAYS)
    recent_cut, old_cut = as_of - timedelta(days=RECENT_DAYS), as_of - timedelta(days=OLD_EMAIL_DAYS)
    accounts = {a["account_key"]: a for a in read(root, "crm/accounts.csv")}
    opportunities = read(root, "crm/opportunities.csv")
    deals = {o["source_id"]: o for o in opportunities}
    cases = read(root, "support/cases.csv")
    arcs = read(root, "arcs.csv")
    story = {k for a in arcs for k in a["account_key"].split(",")} - {"", "*"}
    # A follow-up is what makes trouble ACKNOWLEDGED, so one on a troubled account changes its answer.
    troubled = story | set(CONTROLS) \
        | {c["account_key"] for c in cases if c["status"] == "open"} \
        | {i["account_key"] for i in read(root, "billing/invoices.csv") if i["status"] != "paid"}

    contacts = read(root, "crm/contacts.csv")
    for n, c in enumerate(read(ADDITIONS, "contacts.csv")):
        a = accounts[c["account_key"]]
        assert c["email"].endswith("@" + c["account_key"]), c["email"]
        contacts.append({**dict.fromkeys(contacts[0], ""), **c, "owner": a["owner"], "city": a["city"],
                         "region": a["region"], "country": a["country"], "source_id": str(FIRST_CONTACT_ID + n)})
    person = {c["email"]: c for c in contacts}
    assert len(person) == len(contacts), "duplicate contact email"
    assert 120 <= len(contacts) <= 140, f"{len(contacts)} contacts"
    assert {c["owner"] for c in contacts} <= set(SALES), "a contact owned by someone outside sales"
    families = {"accounts": accounts.values(), "contacts": contacts, "deals": opportunities, "cases": cases}
    ids = {name: {r["source_id"] for r in rows} for name, rows in families.items()}
    for x in ids:
        for y in ids:
            assert x >= y or not ids[x] & ids[y], f"{x} and {y} share ids {sorted(ids[x] & ids[y])}"
    print("assert ok: account, contact, deal and case ids are disjoint")
    per_account = Counter(c["account_key"] for c in contacts)
    thin = sorted({o["account_key"] for o in opportunities if o["status"] == "open"} - {SANDBOX}
                  - {k for k, n in per_account.items() if n >= 3})
    assert not thin, f"accounts with an open deal and fewer than 3 contacts: {thin}"

    emails, calls = read(ADDITIONS, "emails.csv"), read(ADDITIONS, "calls.csv")
    touches, deal_touches, connected = defaultdict(list), defaultdict(list), defaultdict(list)
    for kind, rows, at in (("email", emails, "sent_at"), ("call", calls, "called_at")):
        assert len({r["source_id"] for r in rows}) == len(rows), f"duplicate {kind} source_id"
        for r in rows:
            who = person[r["contact_email"]]
            assert r["account_key"] == who["account_key"], f"{r['source_id']} account is not its contact's"
            assert r["owner"] in OWNERS and r["direction"] in ("outbound", "inbound"), r["source_id"]
            assert kind == "email" or r["outcome"] in ("connected", "voicemail", "no_answer"), r["source_id"]
            when = day(r[at])
            assert date(2026, 1, 1) <= when < as_of, f"{r['source_id']} dated {when}"
            text = " ".join(r[k] for k in ("subject", "title", "body") if k in r)
            pattern = FORBIDDEN.get(r["account_key"])
            assert not (pattern and re.search(pattern, text, re.I)), f"{r['source_id']} breaks an arc's must-not"
            touches[r["contact_email"]].append((when, kind, r["direction"]))
            if kind == "call" and r["outcome"] == "connected":
                connected[r["contact_email"]].append(when)
            if r["opportunity_id"]:
                assert deals[r["opportunity_id"]]["account_key"] == r["account_key"], r["source_id"]
                deal_touches[r["opportunity_id"]].append((when, r["direction"]))
    for m in read(root, "crm/meetings.csv"):
        if m["attendee_email"]:
            touches[m["attendee_email"]].append((day(m["starts_at"]), "meeting", "outbound"))

    # HubSpot leaves inbound email out of "last contacted"; every set must hold either way.
    def newest(email, kinds, outbound_only):
        return max((w for w, k, d in touches[email] if k in kinds and not (outbound_only and d == "inbound")),
                   default=None)

    def quiet(kinds, outbound_only):
        out = {o: set() for o in SALES}
        for c in contacts:
            w = newest(c["email"], kinds, outbound_only)
            if w:
                check_far(w, quiet_cut, f"{c['email']}'s newest {'/'.join(sorted(kinds))}")
            if not w or w <= quiet_cut:
                out[c["owner"]].add(c["email"])
        return out

    for o, e in EMAIL_CONTROL.items():
        assert person[e]["owner"] == o and e not in QUIET[o], e
        assert touches[e] and newest(e, EMAIL, False) <= old_cut, f"control {e} needs an email {OLD_EMAIL_DAYS}+ days old"
        assert any(w >= recent_cut for w in connected[e]), f"control {e} needs a connected call in {RECENT_DAYS} days"
    for c in contacts:
        e = c["email"]
        if e not in QUIET[c["owner"]] and e != EMAIL_CONTROL[c["owner"]]:
            assert any(k == "email" and d == "outbound" and w >= recent_cut for w, k, d in touches[e]), \
                f"{e} needs an outbound email in the {RECENT_DAYS} days before {as_of}"
    for outbound_only in (False, True):
        reading = "outbound email only" if outbound_only else "any email"
        gone = quiet(ANY, outbound_only)
        assert gone == QUIET, f"gone quiet ({reading}): {gone}"
        unmailed = quiet(EMAIL, outbound_only)
        assert unmailed == {o: QUIET[o] | {EMAIL_CONTROL[o]} for o in SALES}, f"not emailed ({reading}): {unmailed}"
        print(f"assert ok: gone quiet and not emailed, {reading}: 6 and 7 per salesperson")

    open_deals = {i for i, o in deals.items() if o["status"] == "open"}
    for outbound_only in (False, True):
        newest_deal = {i: max((w for w, d in deal_touches[i] if not (outbound_only and d == "inbound")), default=None)
                       for i in open_deals}
        for i, w in newest_deal.items():
            if w:
                check_far(w, stall_cut, f"deal {i}'s newest engagement")
        stalled = {i for i, w in newest_deal.items() if not w or w <= stall_cut}
        assert stalled == STALLED, f"stalled deals are {sorted(stalled)}, expected {sorted(STALLED)}"
        assert all(newest_deal[i] for i in STALLED), "a stalled deal needs an engagement to have gone quiet after"
        print(f"assert ok: stalled {sorted(stalled)}, {'outbound email only' if outbound_only else 'any email'}")
    assert STALLED <= set(CLOSE_ON)
    for i, close_on in CLOSE_ON.items():
        deals[i]["close_on"] = close_on
    for i in open_deals:
        check_far(day(deals[i]["close_on"]), as_of, f"deal {i}'s close date")
    slipping = {i for i in open_deals if day(deals[i]["close_on"]) < as_of}
    assert slipping == SLIPPING and not slipping & STALLED, f"slipping deals are {sorted(slipping)}"
    print(f"assert ok: slipping {sorted(slipping)}, disjoint from stalled")
    for i, ts in deal_touches.items():
        deals[i]["modified_on"] = max(deals[i]["modified_on"], max(w for w, _ in ts).isoformat())
    for i in STALLED:
        assert day(deals[i]["modified_on"]) <= stall_cut, f"stalled deal {i} was modified in the window"

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
    late = {o: sorted(f["source_id"] for f in followups if f["owner"] == o and f["status"] == "open"
                      and day(f["due_on"]) < as_of) for o in OWNERS}
    for o in OWNERS:
        mine = [f for f in followups if f["owner"] == o and f["status"] == "open"]
        assert (len(mine), len(late[o])) == (5, 2), f"{o} has {len(mine)} open follow-ups, {len(late[o])} past due"
        assert not {f["account_key"] for f in followups if f["source_id"] in late[o]} & story, \
            f"{o}'s past-due follow-up sits on an arc account"
    print("assert ok: 5 open and 2 past-due follow-ups per owner, none past due on an arc account")

    for c in contacts:
        w = newest(c["email"], ANY, False)
        if w:
            c["last_activity_on"] = w.isoformat()
    when = f"as of {as_of}"
    for o in SALES:
        arcs.append({"arc": "gone quiet", "account_key": "*", "surfaces_as":
                     f"{o}: {', '.join(sorted(QUIET[o]))} - no email, call or meeting in the {QUIET_DAYS} days "
                     f"before, {when}; the same with or without inbound email",
                     "must_not": f"any other contact (each had an outbound email in the {RECENT_DAYS} days before)"})
    for o in SALES:
        e = EMAIL_CONTROL[o]
        arcs.append({"arc": "not emailed", "account_key": "*", "surfaces_as":
                     f"{o}: {', '.join(sorted(QUIET[o] | {e}))} - no email in the {QUIET_DAYS} days before, {when}; "
                     f"{e} is the control: newest email {newest(e, EMAIL, False)}, connected call {max(connected[e])}",
                     "must_not": f"{e} under 'gone quiet' (a call is contact)"})
    arcs.append({"arc": "stalled deals", "account_key": "*", "surfaces_as":
                 f"open deals {', '.join(sorted(STALLED))}: no email or call on the deal in the {STALL_DAYS} days "
                 f"before, {when}; close dates after as-of", "must_not": "any other open deal"})
    arcs.append({"arc": "slipping deals", "account_key": "*", "surfaces_as":
                 f"open deals {', '.join(sorted(SLIPPING))}: close date before as-of, an outbound email or call "
                 f"on the deal within {STALL_DAYS} days, {when}", "must_not": "any stalled deal"})
    for o in OWNERS:
        arcs.append({"arc": "open follow-ups", "account_key": "*", "surfaces_as":
                     f"{o}: 5 open, past due {', '.join(late[o])}, {when}", "must_not": ""})

    tables = {p.relative_to(root).as_posix(): read(root, p.relative_to(root).as_posix())
              for p in sorted(root.rglob("*.csv")) if p.name != "arcs.csv"}
    tables.update({"crm/contacts.csv": contacts, "crm/opportunities.csv": opportunities, "crm/emails.csv": emails,
                   "crm/calls.csv": calls, "crm/followups.csv": followups})
    n = check_text_dates(tables, as_of.year)
    print(f"assert ok: {n} dates in the book are real days, each weekday beside one is right, none day-only")

    return {"crm/contacts": write(root, "crm/contacts.csv", contacts),
            "crm/opportunities": write(root, "crm/opportunities.csv", opportunities),
            "crm/emails": write(root, "crm/emails.csv", emails),
            "crm/calls": write(root, "crm/calls.csv", calls),
            "crm/followups": write(root, "crm/followups.csv", followups),
            "arcs": write(root, "arcs.csv", arcs)}
