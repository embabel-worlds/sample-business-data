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

# HubSpot's default pipeline, in order. Won and lost are outcomes, not steps, so they are
# carried as `status` and left out of the ordering.
STAGES = ["Appointment Scheduled", "Qualified to Buy", "Presentation Scheduled",
          "Decision Maker Bought-In", "Contract Sent"]
PRIORITY = {"p0": "urgent", "p1": "high", "p2": "medium", "p3": "low", "p4": "low"}
KINDS = {"bug", "feature-request", "enhancement", "question", "documentation", "security"}


def read(path):
    with open(ROOT / "csv" / path, newline="") as f:
        return list(csv.DictReader(f))


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

    counts.update(apply_arcs.apply(ROOT / "book"))
    counts.update(apply_engagements.apply(ROOT / "book", AS_OF))
    rewrite_domains(ROOT / "book")
    (ROOT / "book" / "book.json").write_text(json.dumps({"as_of": AS_OF, "rows": counts}, indent=2) + "\n")
    for name, n in counts.items():
        print(f"{name}  {n}")


if __name__ == "__main__":
    main()
