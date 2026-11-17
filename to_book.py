"""Turn the product-shaped CSVs into a neutral BOOK that any product's loader can read.

csv/ speaks HubSpot, Stripe and GitHub, because that is how the data was authored. A loader
for Odoo should not have to know what a HubSpot lifecycle stage is, and a loader for Zammad
should not have to parse GitHub labels. So this script does that translation once, into a
vocabulary with no product in it:

    book/crm/        accounts, contacts, opportunities
    book/support/    cases
    book/billing/    customers, subscriptions, invoices, payments, refunds, disputes
    book/book.json   the as-of date and the row counts

and then lays the demo's story arcs over it (apply_arcs.py), which adds crm/notes, crm/meetings
and arcs.csv.

The arithmetic is the point. With D datasets and P products, product-shaped loaders cost
D x P. With a book in the middle it is D + P: a new dataset writes one of these scripts and
every loader works; a new product writes one loader and every dataset works.

One key joins everything: `account_key`, the customer's registrable domain. It is the only
identifier every product can hold and no product invented.

    python3 to_book.py            # write book/
"""

import calendar
import csv
import json
import re
from pathlib import Path

import apply_arcs
import apply_engagements

ROOT = Path(__file__).parent

# The day the billing and support data treat as "today" (the workbooks' own version date).
# Loaders that want the story to stay current turn dates into ages relative to this.
AS_OF = "2026-06-27"
NOTES_WRITTEN = "2026-05-01"

# HubSpot's default pipeline, in order. Won and lost are outcomes, not steps, so they are
# carried as `status` and left out of the ordering.
STAGES = ["Appointment Scheduled", "Qualified to Buy", "Presentation Scheduled",
          "Decision Maker Bought-In", "Contract Sent"]
PRIORITY = {"p0": "urgent", "p1": "high", "p2": "medium", "p3": "low", "p4": "low"}
KINDS = {"bug", "feature-request", "enhancement", "question", "documentation", "security"}


# The workbooks write "sent 4/22"; a loader that moves dates reads "April 22" and not 4/22.
MONTH_DAY = re.compile(r"(?<![\d/])(1[0-2]|[1-9])/(3[01]|[12]\d|[1-9])(?![\d/])")
# Nor can it move "in March", "Q3" or "2027", which stop being true once the dates around them move. Each
# becomes the day its own row's fields give, or wording relative to the text's own date. Keyed by the row's id.
REWORD = {
    "hubspot/companies.csv": {
        "201": [("Expanding into EMEA in 2026.", "Expanding into EMEA.")],
        "205": [("through 2027.", "through 2027-05-15."), ("potential next year.", "potential.")],
        "213": [("expecting close in May.", "expecting close within a month.")],
        "215": [("Closed-lost in March", "Closed-lost on March 20"), ("Re-engage Q4 2026.", "Re-engage from 2026-10-01.")],
        "216": [("Renewal in November", "Renewal on 2026-11-25")],
        "223": [("Try again Q3 2026.", "Try again from July 1.")],
        "227": [("Renewed December 2025.", "Renewed 2025-12-04.")],
        "248": [("Researching for Q3 implementation.", "Researching for an implementation by 2026-09-30.")],
    },
    "hubspot/contacts.csv": {
        "101": [("in EMEA next quarter.", "in EMEA in a few months.")],
        "102": [("Ran POC in March,", "Ran a POC about two months ago,")],
        "103": [("Budget cycle starts in July.", "Budget cycle starts in about two months.")],
        "105": [("user conference in October.", "user conference in about five months.")],
        "111": [("add-on in April.", "add-on on April 15."), ("to her sister team next year.", "to her sister team in a year or so."),
                ("Schedule QBR for July.", "Schedule the next QBR in about ten weeks.")],
        "115": [("Lost deal in March", "Lost deal on March 20"),
                ("Re-engage in Q4 2026 when new fiscal year starts.", "Re-engage from 2026-10-01, when their new fiscal year starts.")],
        "116": [("Renewal up in November.", "Renewal up on 2026-11-25.")],
        "122": [("Last QBR in March was positive.", "Last QBR, about six weeks ago, was positive.")],
        "123": [("try again in Q3.", "try again from July 1.")],
        "127": [("Renewed last December.", "Renewed 2025-12-04.")],
        "148": [("Researching for Q3 implementation.", "Researching for an implementation by 2026-09-30.")],
    },
    "hubspot/deals.csv": {
        "315": [("Re-engage Q4 2026.", "Re-engage from 2026-10-01.")],
        "338": [("Duff Beer - Q3 Implementation", "Duff Beer - Brewery Implementation"),
                ("Q3 implementation target.", "Implementation target 2026-09-30.")],
        "349": [("QBR scheduled July.", "QBR scheduled.")],
        "308": [("Expansion play next year.", "Expansion play as they hire.")],
        "309": [("targeted for next year.", "targeted for about a year after this add-on.")],
        # Amsterdam about four months after the 2026-09-15 close, as the emails and calls about it say.
        "344": [("EMEA expansion deal for next year.", "EMEA expansion deal; Amsterdam goes live about four months after it closes.")],
    },
    "github-issues/issues.csv": {
        "1238": [("needed by Q3.", "needed by July 1.")],
        "1296": [("rolling out next quarter.", "rolling out from July 1.")],
    },
    "stripe/customers.csv": {
        "cus_AcmeCorp00001": [("since 2024.", "since 2024-03-28.")],
        "cus_OscorpInd00003": [("added in April.", "added on April 15.")],
        "cus_Tyrell0000004": [("added March 2026.", "added March 22.")],
        "cus_Cyberlife000005": [("renewal in Feb 2026.", "renewal on February 10.")],
        "cus_Dharma00000006": [("Renewed Dec 2025.", "Renewed 2025-12-04.")],
        "cus_Glimmerford00000007": [("purchased March 2026.", "purchased March 15.")],
        "cus_FerrariT00008": [("Renewed April 2026.", "Renewed April 22.")],
        "cus_ChumBucket0009": [("sent April 2026.", "sent ahead of the May 5 renewal.")],
        "cus_LosPollos00011": [("locations April 2026.", "locations April 20.")],
        "cus_Spacely00000012": [("New customer Feb 2026. Reporting module add-on March 2026.",
                                 "New customer since February 25. Reporting module add-on March 30.")],
        "cus_Vandelay000014": [("canceled March 2026", "canceled March 20")],
        "cus_Hudsucker00015": [("Canceled Sept 2025", "Canceled 2025-09-15")],
        # The workbook said February, but its last successful payment is 2025-03-28.
        "cus_Sirius0000016": [("Last payment Feb 2026.", "Last payment 2025-03-28.")],
        "cus_Bluth00000017": [("April invoice failed", "The invoice of April 3 failed")],
    },
    "stripe/subscriptions.csv": {
        "sub_StarkPlatform02": [("through 2027.", "through 2027-05-15.")],
        "sub_OscorpResearch4": [("Closed April 2026.", "Closed April 15.")],
        "sub_TyrellBase0005": [("Renewal Nov 2026.", "Renewal 2026-11-25.")],
        "sub_TyrellSupport06": [("Closed March 2026.", "Closed March 22.")],
        "sub_Cyberlife00007": [("renewal Feb 2026.", "renewal February 10.")],
        "sub_GlimmerfordProd0010": [("Closed March 2026.", "Closed March 15.")],
        "sub_FerrariT000011": [("Renewed April 2026.", "Renewed April 22.")],
        "sub_ChumBucket0012": [("sent April 2026", "sent ahead of the May 5 renewal")],
        "sub_Wernham000013": [("Renewed April 2026.", "Renewed April 8.")],
        "sub_LosPollos00014": [("added April 2026.", "added April 20.")],
        "sub_Spacely000015": [("New customer Feb 2026.", "New customer since February 25.")],
        "sub_Hudsucker00019": [("Canceled Sept 2025", "Canceled 2025-09-15")],
    },
    "stripe/invoices.csv": {
        "in_oscorp_2026_001": [("Due July 2026.", "Due July 18.")],
        "in_hudsucker_2025_001": [("canceled Sept,", "canceled 2025-09-15,")],
    },
    "stripe/charges.csv": {
        **{f"ch_bluth_2026_00{n}": [(f"Bluth {m} 2026", f"Bluth, invoice of {calendar.month_name[n]} 3")]
           for n, m in ((1, "Jan"), (2, "Feb"), (3, "Mar"))},
        **{f"ch_bluth_2026_004{x}": [(f"Bluth April - {n}", f"Bluth, invoice of April 3: {n}")] for x, n in zip("abc", ("1st", "2nd", "3rd"))},
    },
}


def reword(path, r):
    for old, new in REWORD.get(path, {}).pop(next(iter(r.values())), []):
        k = next((k for k, v in r.items() if old in v), None)
        assert k, f"{path}: '{old}' is no longer in its row; update REWORD"
        r[k] = r[k].replace(old, new)
    return r


def read(path):
    with open(ROOT / "csv" / path, newline="") as f:
        return [reword(path, {k: MONTH_DAY.sub(lambda m: f"{calendar.month_name[int(m[1])]} {m[2]}", v)
                              for k, v in r.items()}) for r in csv.DictReader(f)]


def write(path, rows):
    out = ROOT / "book" / path
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def rewrite_domains(book):
    """Move every company onto `<name>.example.com`, last, across every file of the book.

    Several workbook domains belong to real businesses, and a fictional customer joined to live
    enrichment or news by domain would attract a real company's headlines. `example.com` is
    reserved, so nothing here can reach anyone. It is `.example.com` and not `.example` because
    a CRM validates contact emails, and HubSpot rejects the reserved `.example` top level."""
    files = sorted(book.rglob("*.csv"))
    tables = {p: list(csv.reader(open(p, newline=""))) for p in files}
    domains = set()
    for rows in tables.values():
        keys = [i for i, h in enumerate(rows[0]) if h == "account_key"]
        for row in rows[1:]:
            domains |= {k for i in keys for k in row[i].split(",")} - {"", "*"}
            domains |= {m.lower() for cell in row for m in re.findall(r"@([\w.-]+\w)", cell)}
    to = {d: d.split(".")[0] + ".example.com" for d in domains}
    assert len(set(to.values())) == len(to), "two domains would merge into one account"
    pattern = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, sorted(to, key=len, reverse=True))) + r")(?![\w-])", re.I)
    for path, rows in tables.items():
        with open(path, "w", newline="") as f:
            csv.writer(f, lineterminator="\n").writerows(
                [[pattern.sub(lambda m: to[m.group(1).lower()], cell) for cell in row] for row in rows])
    left = {m for p in files for m in re.findall(r"@([\w.-]+\w)", p.read_text())} - set(to.values())
    assert not left, f"addresses outside example.com: {left}"


def main():
    print(f"assert ok: {len(apply_engagements.self_test())} text-date probes give their expected outcome")
    companies = read("hubspot/companies.csv")
    key_by_name = {c["Company Name"]: c["Domain"] for c in companies}
    key_by_id = {c["Record ID"]: c["Domain"] for c in companies}
    contacts = read("hubspot/contacts.csv")
    email_by_name = {f'{c["First Name"]} {c["Last Name"]}': c["Email"] for c in contacts}
    counts = {}

    counts["crm/accounts"] = write("crm/accounts.csv", [{
        "account_key": c["Domain"], "name": c["Company Name"], "website": c["Website"],
        "phone": c["Phone Number"], "industry": c["Industry"], "city": c["City"],
        "region": c["State/Region"], "country": c["Country"], "owner": c["Company Owner"],
        "relationship": c["Type"].lower(), "annual_revenue": c["Annual Revenue"],
        "employees": c["Number of Employees"], "created_on": c["Create Date"],
        "note": c["Description"], "source_id": c["Record ID"],
    } for c in companies])

    counts["crm/contacts"] = write("crm/contacts.csv", [{
        "email": c["Email"], "first_name": c["First Name"], "last_name": c["Last Name"],
        "job_title": c["Job Title"], "phone": c["Phone Number"],
        "account_key": key_by_name[c["Company Name"]], "owner": c["Contact Owner"],
        "city": c["City"], "region": c["State/Region"], "country": c["Country"],
        "created_on": c["Create Date"], "last_activity_on": c["Last Activity Date"],
        "note": c["Notes"], "source_id": c["Record ID"],
        # The workbooks' CRM notes were written on NOTES_WRITTEN, or when the contact was added if that was later.
        "note_on": max(NOTES_WRITTEN, c["Create Date"]) if c["Notes"] else "",
    } for c in contacts])

    def outcome(stage):
        return {"Closed Won": "won", "Closed Lost": "lost"}.get(stage, "open")

    counts["crm/opportunities"] = write("crm/opportunities.csv", [{
        "source_id": d["Record ID"], "title": d["Deal Name"],
        "account_key": key_by_name[d["Associated Company"]],
        "contact_email": email_by_name[d["Associated Contact"]],
        "pipeline": d["Pipeline"], "stage": d["Deal Stage"],
        "stage_order": STAGES.index(d["Deal Stage"]) + 1 if d["Deal Stage"] in STAGES else "",
        "status": outcome(d["Deal Stage"]), "amount": d["Amount"], "currency": "USD",
        "probability": d["Probability"], "close_on": d["Close Date"], "owner": d["Deal Owner"],
        "priority": d["Priority"].lower(), "kind": d["Deal Type"],
        "created_on": d["Create Date"], "modified_on": d["Last Modified Date"],
        "note": d["Description"],
    } for d in read("hubspot/deals.csv")])

    # An issue with no reporter is the vendor's own engineering work, not a customer's case.
    # A support desk never saw it, so it is not in the book; the count records how many.
    issues = read("github-issues/issues.csv")
    cases = []
    for i in issues:
        if not i["Reporter Company (HubSpot)"]:
            continue
        labels = [l.strip() for l in i["Labels"].split(",") if l.strip()]
        cases.append({
            "source_id": i["Issue #"], "subject": i["Title"],
            "account_key": key_by_name[i["Reporter Company (HubSpot)"]],
            # A support desk knows who a requester says they work for without ever having
            # seen the CRM, so the name travels with the case rather than being looked up.
            "account_name": i["Reporter Company (HubSpot)"],
            "requester_email": email_by_name[i["Reporter Contact (HubSpot)"]],
            "requester_name": i["Reporter Contact (HubSpot)"],
            "status": "resolved" if i["State"] == "closed" else "open",
            "priority": next((PRIORITY[l] for l in labels if l in PRIORITY), "none"),
            "kind": next((l for l in labels if l in KINDS), ""),
            "labels": ",".join(l for l in labels if l not in PRIORITY and l not in KINDS),
            # Filed by the vendor's own staff after a call or a demo: the customer never
            # wrote these words, so a loader must not put them in the customer's mouth.
            "filed_on_behalf": "yes" if "filed-on-behalf" in labels else "no",
            "filed_by": i["Author"], "engineers": i["Assignees"], "milestone": i["Milestone"],
            "opened_on": i["Created At"], "updated_on": i["Updated At"], "closed_on": i["Closed At"],
            "reply_count": i["Comments"], "body": i["Body"],
        })
    counts["support/cases"] = write("support/cases.csv", cases)
    counts["support/cases_left_out_as_internal"] = len(issues) - len(cases)

    customers = read("stripe/customers.csv")
    billing_key = {c["Customer ID"]: key_by_id.get(c["HubSpot Company ID"]) or c["Email"].split("@")[1]
                   for c in customers}
    counts["billing/customers"] = write("billing/customers.csv", [{
        "source_id": c["Customer ID"], "account_key": billing_key[c["Customer ID"]],
        "name": c["Name"], "email": c["Email"], "phone": c["Phone"], "currency": c["Currency"],
        "country": c["Country"], "payment_method": c["Default Payment Method"],
        "delinquent": c["Delinquent"].lower(), "balance_owed": c["Account Balance"],
        "created_on": c["Created Date"], "known_to_crm": "yes" if c["HubSpot Company ID"] else "no",
        "note": c["Description"],
    } for c in customers])

    counts["billing/subscriptions"] = write("billing/subscriptions.csv", [{
        "source_id": s["Subscription ID"], "customer_id": s["Customer ID"],
        "account_key": billing_key[s["Customer ID"]], "status": s["Status"], "product": s["Product"],
        "plan_code": s["Price ID"], "amount": s["Amount per Period"], "currency": s["Currency"],
        "interval": s["Billing Interval"], "seats": s["Quantity (Seats)"],
        "started_on": s["Start Date"], "period_start": s["Current Period Start"],
        "period_end": s["Current Period End"], "canceled_on": s["Canceled At"], "note": s["Notes"],
    } for s in read("stripe/subscriptions.csv")])

    counts["billing/invoices"] = write("billing/invoices.csv", [{
        "source_id": v["Invoice ID"], "number": v["Invoice Number"], "customer_id": v["Customer ID"],
        "account_key": billing_key[v["Customer ID"]], "subscription_id": v["Subscription ID"],
        "status": v["Status"], "amount_due": v["Amount Due"], "amount_paid": v["Amount Paid"],
        "currency": v["Currency"], "issued_on": v["Created Date"], "due_on": v["Due Date"],
        "paid_on": v["Paid At"], "description": v["Description"],
    } for v in read("stripe/invoices.csv")])

    counts["billing/payments"] = write("billing/payments.csv", [{
        "source_id": p["Charge ID"], "invoice_id": p["Invoice ID"], "customer_id": p["Customer ID"],
        "account_key": billing_key[p["Customer ID"]], "amount": p["Amount"], "currency": p["Currency"],
        "status": p["Status"], "attempted_on": p["Created Date"], "method": p["Payment Method"],
        "failure_code": p["Failure Code"], "refunded": p["Refunded"].lower(),
        "disputed": p["Disputed"].lower(), "description": p["Description"],
    } for p in read("stripe/charges.csv")])

    counts["billing/refunds"] = write("billing/refunds.csv", [{
        "source_id": r["Refund ID"], "payment_id": r["Charge ID"], "customer_id": r["Customer ID"],
        "account_key": billing_key[r["Customer ID"]], "amount": r["Amount"], "currency": r["Currency"],
        "reason": r["Reason"], "refunded_on": r["Created Date"], "description": r["Description"],
    } for r in read("stripe/refunds.csv")])

    counts["billing/disputes"] = write("billing/disputes.csv", [{
        "source_id": d["Dispute ID"], "payment_id": d["Charge ID"], "customer_id": d["Customer ID"],
        "account_key": billing_key[d["Customer ID"]], "amount": d["Amount"], "currency": d["Currency"],
        "status": d["Status"], "reason": d["Reason"], "opened_on": d["Created Date"],
        "respond_by": d["Evidence Due By"], "description": d["Description"],
    } for d in read("stripe/disputes.csv")])

    assert not any(REWORD.values()), f"REWORD rows not in csv/: {REWORD}"
    counts.update(apply_arcs.apply(ROOT / "book"))
    counts.update(apply_engagements.apply(ROOT / "book", AS_OF))
    rewrite_domains(ROOT / "book")
    (ROOT / "book" / "book.json").write_text(json.dumps({"as_of": AS_OF, "rows": counts}, indent=2) + "\n")
    for name, n in counts.items():
        print(f"{name}  {n}")


if __name__ == "__main__":
    main()
