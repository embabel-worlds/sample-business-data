"""Regenerate csv/ from the workbooks in source/, and refuse to if the data disagrees with itself.

The workbooks are the authored originals and are never edited here: they are maintained in
Google Sheets, downloaded as Excel, and dropped into source/ unchanged. The CSVs are what
every consumer reads, because a seeder for any product can load a CSV and a pull request
can show a readable diff of one.

Conversion is deliberately dumb. Column names, values and row order are kept exactly as
authored; the only changes are the ones a CSV forces (dates as ISO text, a workbook's blank
spacer rows dropped) and one the data asks for: a totals row is a statement ABOUT the rows,
not a row, so it is lifted out and checked instead of being written as a fiftieth deal.

The checks exist because these three workbooks claim to describe one business. If a Stripe
customer points at a HubSpot company that is not there, every demo built on the join is
wrong in a way nobody will notice from the inside — so that is an error here, once.

    python3 convert.py            # write csv/, run the checks
    python3 convert.py --check    # run the checks only; write nothing
"""

import csv
import datetime
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).parent

# workbook file -> the directory its tabs land in. The README tab of each becomes README.txt
# beside them, because the author's notes on linking and edge cases are part of the data.
WORKBOOKS = {
    "hubspot_sample_data.xlsx": "hubspot",
    "stripe-sample-data-v1-2026-06-27.xlsx": "stripe",
    "github-issues-sample-data-v1-2026-06-27.xlsx": "github-issues",
}


def slug(title):
    return title.strip().lower().replace(" ", "_")


def cell(value):
    """A cell as CSV text. Dates lose a midnight time that Sheets added and nobody wrote."""
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.date().isoformat() if value.time() == datetime.time(0) else value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def read_workbook(path):
    """Every tab as (header, rows, trailing), where trailing is whatever follows a blank row."""
    # data_only: a totals cell is a formula, and the checks need the number Sheets computed.
    book = openpyxl.load_workbook(path, data_only=True)
    tabs = {}
    for sheet in book:
        rows = [[cell(v) for v in row] for row in sheet.iter_rows(values_only=True)]
        if sheet.title == "README":
            tabs["README"] = rows
            continue
        header, body, trailing, seen_blank = rows[0], [], [], False
        for row in rows[1:]:
            if not any(row):
                seen_blank = True
            elif seen_blank:
                trailing.append(row)
            else:
                body.append(row)
        tabs[sheet.title] = (header, body, trailing)
    return tabs


def column(tab, name):
    header, body, _ = tab
    i = header.index(name)
    return [row[i] for row in body]


def check(data):
    """Return a list of problems. Empty means the three workbooks agree with each other."""
    problems = []
    hub, stripe, issues = data["hubspot"], data["stripe"], data["github-issues"]

    def must_be_in(what, values, allowed, allow_blank=False):
        for v in values:
            if (v or not allow_blank) and v not in allowed:
                problems.append(f"{what}: {v!r} does not exist")

    companies = set(column(hub["Companies"], "Company Name"))
    company_ids = set(column(hub["Companies"], "Record ID"))
    contacts = {f"{f} {l}" for f, l in zip(column(hub["Contacts"], "First Name"), column(hub["Contacts"], "Last Name"))}

    must_be_in("contact's company", column(hub["Contacts"], "Company Name"), companies)
    must_be_in("deal's company", column(hub["Deals"], "Associated Company"), companies)
    must_be_in("deal's contact", column(hub["Deals"], "Associated Contact"), contacts)

    # Blank is meaningful, not missing: a Stripe customer with no HubSpot company is one the
    # CRM has never heard of, and the author put those there on purpose.
    must_be_in("stripe customer's HubSpot company", column(stripe["Customers"], "HubSpot Company ID"), company_ids, allow_blank=True)
    customers = set(column(stripe["Customers"], "Customer ID"))
    invoices = set(column(stripe["Invoices"], "Invoice ID"))
    charges = set(column(stripe["Charges"], "Charge ID"))
    for tab in ("Subscriptions", "Invoices", "Charges", "Refunds", "Disputes"):
        must_be_in(f"stripe {tab.lower()} customer", column(stripe[tab], "Customer ID"), customers)
    must_be_in("charge's invoice", column(stripe["Charges"], "Invoice ID"), invoices, allow_blank=True)
    must_be_in("refund's charge", column(stripe["Refunds"], "Charge ID"), charges)
    must_be_in("dispute's charge", column(stripe["Disputes"], "Charge ID"), charges)

    must_be_in("issue reporter's company", column(issues["Issues"], "Reporter Company (HubSpot)"), companies, allow_blank=True)
    must_be_in("issue reporter", column(issues["Issues"], "Reporter Contact (HubSpot)"), contacts, allow_blank=True)

    # The Deals tab states its own total and weighted pipeline. Recompute both from the rows.
    _, _, trailing = hub["Deals"]
    if trailing:
        stated = [float(v) for v in trailing[0] if v.replace(".", "", 1).isdigit()]
        amounts = [float(a) for a in column(hub["Deals"], "Amount")]
        weights = [float(p) for p in column(hub["Deals"], "Probability")]
        total, weighted = sum(amounts), sum(a * p for a, p in zip(amounts, weights))
        if len(stated) != 2 or abs(stated[0] - total) > 0.5 or abs(stated[1] - weighted) > 0.5:
            problems.append(f"deals totals row states {stated}, rows give {total:.0f} and {weighted:.0f}")
    return problems


def main():
    write = "--check" not in sys.argv
    data = {directory: read_workbook(ROOT / "source" / file) for file, directory in WORKBOOKS.items()}

    for directory, tabs in data.items():
        out = ROOT / "csv" / directory
        if write:
            out.mkdir(parents=True, exist_ok=True)
        for title, tab in tabs.items():
            if title == "README":
                if write:
                    lines = ["  ".join(v for v in row if v).rstrip() for row in tab]
                    (out / "README.txt").write_text("\n".join(lines).strip() + "\n")
                continue
            header, body, _ = tab
            print(f"{directory}/{slug(title)}.csv  {len(body)} rows")
            if write:
                with open(out / f"{slug(title)}.csv", "w", newline="") as f:
                    writer = csv.writer(f, lineterminator="\n")
                    writer.writerow(header)
                    writer.writerows(body)

    problems = check(data)
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    print("checks:", "FAILED" if problems else "passed")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
