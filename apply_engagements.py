"""Add the CRM's day-to-day history to the book: more people, the emails and calls sales logged,
and the follow-ups each owner has open. `to_book.py` runs it after `apply_arcs.py`.

The workbooks hold one contact per company and no correspondence, so a question a salesperson
asks every Monday has nothing to answer from: who have I gone quiet on, which deals have stalled,
what is overdue on my list. The rows are in `additions/`, drafted once and committed, so the book
stays deterministic; this script checks them against the book and writes

    crm/contacts.csv       the drafted people appended, ids from 501; owner and location come from
                           their account, `last_activity_on` is their newest email, call or meeting,
                           `note_on` the day their note was written
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
# A loader moves the dates inside texts as it moves the date fields: ISO, "June 16" or "Jun. 16th", "16 June" or
# "16th June", the month capitalised (load_book.py's DATES). It moves them by whole weeks, so a weekday beside a
# date stays true.
MONTH = "|".join(sorted({n for m in calendar.month_name[1:] for n in (m, m[:3])} | {"Sept"}, key=len, reverse=True))
TEXT_DATE = re.compile(rf"(?:\b(?P<wd>{'|'.join(calendar.day_name)}),? )?(?:\b(?P<iso>\d{{4}}-\d\d-\d\d)\b"
                       rf"|\b(?P<m>{MONTH})\.? (?P<d>\d{{1,2}})(?:st|nd|rd|th)?\b"
                       rf"|\b(?P<d2>\d{{1,2}})(?:st|nd|rd|th)? (?P<m2>{MONTH})\b)")
# Only free text carries dates a loader moves; a name, an email or an id is never read as one ("June" Kowal).
TEXT_COLUMNS = {"note", "body", "subject", "title", "summary", "description"}
# A loader reads a month-day without a year in the book's year and writes it back without one, so a moved date
# must stay in that year. shortcut: holds for loads up to 20 weeks after as-of (as-of 2026-06-27 lands on
# 2026-11-14); a later load needs more dates in ISO, or a loader that writes the year.
SHIFT_HORIZON = timedelta(weeks=20)
# The gate is strict, not a reader of English: every word below that could name a time is rejected unless it is
# part of a date the loader moves, or sits inside an ALLOWED phrase.
MONTH_WORD = re.compile(rf"(?i)\b(?:{MONTH})\b")
HOLIDAY_DAY = (r"labou?r|memorial|independence|boxing|mother'?s|father'?s|valentine'?s|presidents'?|veterans'?"
               r"|columbus|martin luther king|mlk|victoria|canada|australia|anzac|bastille|remembrance|armistice"
               r"|groundhog|election|new year'?s|st\.? patrick'?s")
PERIOD = re.compile(
    r"(?<![\w.+-])(?:19|20)\d\d(?!\w|\.\d)|\b[A-Z][a-z]+(?:'s|s')? Day\b|(?i:\b(?:q[1-4]|h[12])\b"
    r"|\b(?:spring|summer|autumn|fall|winter)s?\b"
    r"|\b(?:christmas|xmas|thanksgiving|easter|hanukkah|diwali|ramadan|eid|passover|halloween|juneteenth"
    r"|new year'?s?|black friday|cyber monday|good friday|holidays?)\b"
    rf"|\b(?:{HOLIDAY_DAY}) day\b"
    r"|\b(?:fiscal|financial|academic|school) years?\b|\bsemesters?\b|\b(?:year|month|quarter)[- ]to[- ]date\b|\b[ymq]td\b"
    r"|\b(?:next|last|this|coming|past)(?:\s+[\w'-]+){0,2}?\s+(?:months?|years?|quarters?|halves"
    r"|half(?!\s+(?:an\s+)?hours?)|weeks?\s+of\s+the\s+year|calendar\s+weeks?)\b"
    r"|\bquarters\b|\b(?:month|quarter|year)[- ]end\b|\bmid[- ]?(?:month|year)\b"
    r"|\b(?:end|start|beginning|middle|rest) of (?:the|this|next|last) (?:month|year|quarter)\b"
    r"|\b(?:earlier|later) (?:this|that|in the) (?:month|year)\b)")
# What it cannot move: a day without its month, or a numeric month/day.
DAY_ONLY = re.compile(r"\bthe \d{1,2}(?:st|nd|rd|th)\b|(?<![\d/])\d{1,2}/\d{1,2}(?![\d/])")
# A day that borrows its month from a date beside it: "June 10 &11", "June 10, 11", "June 10 - 12", "10-12 June".
# The loader moves the date, not the day.
ORD = r"\d{1,2}(?:st|nd|rd|th)?"
JOIN = r"\s*(?:[,/;&–—-]|(?<!\w)(?:and|or|to|through|till|until)(?!\w))\s*(?:(?:and|or)\s+)?"
ELIDED = re.compile(rf"{JOIN}{ORD}\b(?!\s*(?:{MONTH})\b)")
ELIDED_BEFORE = re.compile(rf"\b{ORD}{JOIN}$")
# The only exceptions: exact phrases from the Book's own texts, each a deliberate decision. A new text that trips
# the gate is rewritten, or its exact phrase is added here with the reason it names no time.
ALLOWED = {
    "May not be a real prospect": "the verb 'may' (contact 144's note)",
    "she may be slow to respond": "the verb 'may' (email-0014)",
    "when their new fiscal year starts": "an event of theirs, dated by the ISO window before it (contact 115's note)",
}
# Each probe: (column, text, the gate accepts it). to_book.py runs these before the book.
PROBES = [
    *[("body", t, False) for t in (
        "Expected go-live: June.", "Meet June 10 &11.", "Live in q3.", "Over labor day.", "Renewal moves to June.",
        "Launch on June.", "June renewal paperwork is ready.", "In the next six months we grow.",
        "Fiscal year ends soon.", "Year to date numbers.", "Meet June 10, 11 and 12.", "Meet June 10–12.",
        "Meet June 10/11.", "Meet June 10; 11 if not.", "Meet June 10 or 11.", "Meet 10-12 June.",
        "Deliver in july.", "Deliver JUNE 10.", "Mid-June works.", "Before Christmas.", "Before Mother's Day.",
        "Upsell in the next two quarters.", "Close this quarter.", "Over the summer.", "Signed in 2027.",
        "Rollout next year.", "Due the 11th.", "Sent 4/22.", "Meet June 31.", "Tuesday, June 10.",
        "Wednesday, June 10, 3 seats.", "Semester review.", "Academic year starts soon.", "Mid-year review.", "By the end of the year.",
        # A month or season word that names no time is rejected too, unless its exact phrase is ALLOWED.
        "May the team proceed?", "The rollout may slip.", "Ask June from finance.", "The fall in revenue.")],
    *[("body", t, True) for t in (
        "Meet June 10 or June 11.", "Meet Jun. 10th or 10th June.", "Meet Wednesday, June 10.", "Due 2026-11-25.",
        "In about six months.", "A quarterly review.", "Join for the last half hour.", "Renews each June 1.")],
    ("first_name", "June", True), ("email", "june.10@x.com", True),
    *[("body", f"{p}.", True) for p in ALLOWED],
]


def day(text):
    return date.fromisoformat(text[:10])


def check_far(when, cut, what):
    assert abs((when - cut).days) > MARGIN, f"{what} on {when} is within {MARGIN} days of the cut-off {cut}"


def check_text_dates(tables, year):
    """Every free text names times only as dates a loader moves - ISO, or a capitalised month with its day and no
    day beside it that borrows its month - each a real day, with a weekday beside it that is its own. Any other
    month word, quarter, half, season, holiday, fiscal period, calendar period relative to the text, period end,
    bare year or day without its month is rejected, unless it sits inside an ALLOWED phrase. A month-day without a
    year is read in `year`, and stays in it when moved by up to SHIFT_HORIZON; a later one is ISO."""
    n = 0
    for name, rows in tables.items():
        for r in rows:
            for k, v in r.items():
                if k not in TEXT_COLUMNS or not isinstance(v, str):
                    continue
                where = f"{name} {r.get('source_id') or r.get('email')} {k}"
                allowed = [m.span() for p in ALLOWED for m in re.finditer(re.escape(p), v)]
                dates = list(TEXT_DATE.finditer(v))
                spans = allowed + [m.span() for m in dates]
                for hit in (*DAY_ONLY.finditer(v), *MONTH_WORD.finditer(v), *PERIOD.finditer(v)):
                    assert any(a <= hit.start() < b for a, b in spans), \
                        f"{where}: '{hit[0]}' names a time a loader cannot move; write a date, or ALLOW the phrase"
                bad = next((m for m in dates if ELIDED.match(v, m.end()) or any(
                    not any(o.start() <= e.start() < o.end() for o in dates) for e in [ELIDED_BEFORE.search(v, 0, m.start())] if e)), None)
                assert not bad, f"{where}: a day beside '{bad and bad[0]}' borrows its month, so a loader cannot move it"
                for m in dates:
                    month, d = (m["m"], m["d"]) if m["m"] else (m["m2"], m["d2"])
                    try:
                        when = date.fromisoformat(m["iso"]) if m["iso"] else \
                            date(year, next(i for i, f in enumerate(calendar.month_name) if i and f.startswith(month[:3])), int(d))
                    except ValueError:
                        raise AssertionError(f"{where}: '{m[0]}' is not a real date")
                    assert m["iso"] or (when + SHIFT_HORIZON).year == year, \
                        f"{where}: '{m[0]}' moved by {SHIFT_HORIZON.days} days lands in the next year; write it ISO"
                    assert not m["wd"] or m["wd"] == calendar.day_name[when.weekday()], \
                        f"{where}: '{m[0]}' but {when} is a {calendar.day_name[when.weekday()]}"
                    n += 1
    return n


def self_test():
    """The probes give their expected outcome; returns them with the outcome for a report."""
    out = []
    for column, text, ok in PROBES:
        try:
            check_text_dates({"probe": [{column: text}]}, 2026)
            got = True
        except AssertionError:
            got = False
        assert got == ok, f"probe {column}={text!r}: {'accepted' if got else 'rejected'}, expected the opposite"
        out.append((column, text, got))
    return out


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
    for c in contacts:  # a note is written once its person is known, and not after as-of
        assert (c["note_on"] == "") if not c["note"] else c["created_on"] <= c["note_on"] <= as_of.isoformat(), \
            f"{c['email']} note_on {c['note_on']!r}, created {c['created_on']}"
    print("assert ok: every contact note is dated between its contact's creation and as-of")
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
    for c in contacts:  # an added person's note is written on the day of their newest logged email or call
        if int(c["source_id"]) >= FIRST_CONTACT_ID and c["note"]:
            logged = max((w.isoformat() for w, _, _ in touches[c["email"]]), default="")
            assert c["note_on"] == logged, f"{c['email']} note_on {c['note_on']}, newest email or call {logged}"
    print("assert ok: every added contact's note is dated on their newest logged email or call")
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
    print(f"assert ok: {n} dates in the book are real days, each weekday beside one is right, and no text names a time a loader cannot move")

    return {"crm/contacts": write(root, "crm/contacts.csv", contacts),
            "crm/opportunities": write(root, "crm/opportunities.csv", opportunities),
            "crm/emails": write(root, "crm/emails.csv", emails),
            "crm/calls": write(root, "crm/calls.csv", calls),
            "crm/followups": write(root, "crm/followups.csv", followups),
            "arcs": write(root, "arcs.csv", arcs)}
