"""Lay the demo's story ARCS over the book, after `to_book.py` has translated the workbooks.

The workbooks were authored as a believable company, not as a demo. Joined, they disagree in
interesting places, but not in every place the account-health demo needs: nobody withholds
payment over a bug, nothing is quietly churning, and no account is noisy but fine. So each
arc the demo plan names (internal-docs product-demo/account-health-demo-plan.md, "One story,
seeded everywhere") is made true here, in the book, where every system's loader will carry
it — never patched into one system afterwards, where a reseed would lose it.

    arc                  account               should surface as
    silent escalation    northwind-traders     at risk; a blind spot (sales unaware)
    quiet churner        chumbucket.com        at risk (failed payments); a blind spot
    withholding          contoso.example       POSSIBLY_WITHHELD_OVER
    acknowledged trouble initech.com           at risk, and NOT a blind spot
    failed payments      acmecorp.com          at risk (failed payments)
    good payer, the 5th  wayfarer-travel       nothing: one failed card, retried next day
    stale deal           globex.io             an open deal untouched since April
    noisy but healthy    brightline-analytics  nothing, despite nine cases
    shared incident      the three export cases  SHARES_ISSUE between them
    controls             four quiet customers  nothing

Group contagion is NOT seeded: the book has no parent/subsidiary links, so there is no group
for trouble to spread through. Inventing one belongs in the book's schema, not in an arc.

It also writes the MANUAL HISTORY an agent is later asked to learn from, as new files:

    crm/notes.csv      notes a person wrote by hand: an AR clerk after every failed card,
                       the account owners on the arcs above
    crm/meetings.csv   every Monday, a salesperson ran the overdue list and booked a call
                       with each account on it, on the Mondays it was not empty
    crm/followups.csv  follow-ups an owner scheduled on an account — work somebody has
                       picked up, which is what an at-risk account being ACKNOWLEDGED means

and `arcs.csv`, one row per arc with what should and must not surface, for the harness.

Every arc's invariant is asserted before anything is written: a book that silently stopped
telling its story would pass every loader and fail every demo. Deterministic: no clock, no
randomness; the same workbooks give the same book byte for byte.
"""

import csv
from datetime import date, timedelta

AR_CLERK = "Dana Whitfield"
# The writes sandbox looks like any small customer; only arcs.csv says what it is for.
SANDBOX = "fernhollow.example"
CONTROLS = ["cyberlife.com", "dharmainit.com", "ferrari-tech.it", "wernham-hogg.co.uk"]
FAILURES = {"card": ["card_declined", "insufficient_funds", "expired_card"],
            "sepa_debit": ["insufficient_funds"], "bacs_debit": ["insufficient_funds"],
            "ach_credit_transfer": ["insufficient_funds"]}
# A charge against the customer's own credit balance cannot bounce, so it has no failures.


def d(text):
    return date.fromisoformat(text)


def read(book, name):
    path = book / name
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write(book, name, rows, fields=None):
    path = book / name
    with open(path, "w", newline="") as f:
        out = csv.DictWriter(f, fieldnames=fields or list(rows[0]), lineterminator="\n")
        out.writeheader()
        out.writerows(rows)
    return len(rows)


def one(rows, **match):
    hits = [r for r in rows if all(r[k] == v for k, v in match.items())]
    assert len(hits) == 1, f"expected one row matching {match}, found {len(hits)}"
    return hits[0]


def blank(rows):
    return dict.fromkeys(rows[0], "")


class Book:
    """The book's tables, held while arcs are laid over them."""

    TABLES = ["crm/accounts", "crm/contacts", "crm/opportunities", "support/cases",
              "billing/customers", "billing/subscriptions", "billing/invoices", "billing/payments"]

    def __init__(self, root):
        self.root = root
        self.t = {name: read(root, name + ".csv") for name in self.TABLES}
        self.notes, self.meetings, self.arcs, self.followups = [], [], [], []
        self.number = max(int(i["number"].split("-")[1]) for i in self.t["billing/invoices"])

    def add(self, table, **values):
        row = blank(self.t[table])
        unknown = set(values) - set(row)
        assert not unknown, f"{table} has no column {unknown}"
        row.update(values)
        self.t[table].append(row)
        return row

    def next_id(self, table):
        return str(max(int(r["source_id"]) for r in self.t[table] if r["source_id"].isdigit()) + 1)

    def invoice_number(self):
        self.number += 1
        return f"INV-{self.number}"

    def followup(self, account_key, owner, scheduled_on, due_on, summary, note=""):
        self.followups.append({"source_id": f"followup-{len(self.followups) + 1:04d}", "account_key": account_key,
                               "owner": owner, "scheduled_on": scheduled_on, "due_on": due_on,
                               "summary": summary, "note": note})

    def note(self, account_key, author, written_on, body, opportunity=""):
        self.notes.append({"source_id": f"note-{len(self.notes) + 1:04d}", "account_key": account_key,
                           "opportunity_id": opportunity, "author": author, "written_on": written_on,
                           "body": body})

    def arc(self, arc, account_key, surfaces_as, must_not=""):
        self.arcs.append({"arc": arc, "account_key": account_key, "surfaces_as": surfaces_as,
                          "must_not": must_not})

    def company(self, key, name, owner, industry, city, region, country, phone, created_on, note,
                contact, title):
        """A new customer, known to the CRM, with one person at it."""
        first, last = contact.split(" ")
        self.add("crm/accounts", account_key=key, name=name, website=f"https://www.{key}", phone=phone,
                 industry=industry, city=city, region=region, country=country, owner=owner,
                 relationship="customer", annual_revenue="", employees="", created_on=created_on,
                 note=note, source_id=self.next_id("crm/accounts"))
        email = f"{first.lower()}.{last.lower()}@{key}"
        self.add("crm/contacts", email=email, first_name=first, last_name=last, job_title=title,
                 phone=phone, account_key=key, owner=owner, city=city, region=region, country=country,
                 created_on=created_on, last_activity_on=created_on, note="",
                 source_id=self.next_id("crm/contacts"))
        return email

    def deal(self, key, email, title, stage, status, amount, probability, close_on, owner, created_on,
             modified_on, note, kind="Existing Business", priority="medium"):
        order = {"Appointment Scheduled": "1", "Qualified to Buy": "2", "Presentation Scheduled": "3",
                 "Decision Maker Bought-In": "4", "Contract Sent": "5"}.get(stage, "")
        return self.add("crm/opportunities", source_id=self.next_id("crm/opportunities"), title=title,
                        account_key=key, contact_email=email, pipeline="Sales Pipeline", stage=stage,
                        stage_order=order, status=status, amount=str(amount), currency="USD",
                        probability=str(probability), close_on=close_on, owner=owner, priority=priority,
                        kind=kind, created_on=created_on, modified_on=modified_on, note=note)

    def case(self, key, account_name, email, person, subject, status, priority, kind, labels, opened_on,
             updated_on, replies, body, closed_on=""):
        return self.add("support/cases", source_id=self.next_id("support/cases"), subject=subject,
                        account_key=key, account_name=account_name, requester_email=email,
                        requester_name=person, status=status, priority=priority, kind=kind, labels=labels,
                        filed_on_behalf="no", filed_by=email.split("@")[0], engineers="", milestone="",
                        opened_on=opened_on, updated_on=updated_on, closed_on=closed_on,
                        reply_count=str(replies), body=body)

    def biller(self, key, cid, name, email, method, created_on):
        self.add("billing/customers", source_id=cid, account_key=key, name=name, email=email, phone="",
                 currency="USD", country="US", payment_method=method, delinquent="no", balance_owed="0",
                 created_on=created_on, known_to_crm="yes", note="")

    def subscription(self, key, cid, sid, product, plan, amount, interval, seats, started_on, period_start,
                     period_end):
        self.add("billing/subscriptions", source_id=sid, customer_id=cid, account_key=key, status="active",
                 product=product, plan_code=plan, amount=str(amount), currency="USD", interval=interval,
                 seats=str(seats), started_on=started_on, period_start=period_start, period_end=period_end)

    def invoice(self, key, cid, iid, sid, amount, issued_on, due_on, paid_on, description, status=None):
        return self.add("billing/invoices", source_id=iid, number=self.invoice_number(), customer_id=cid,
                        account_key=key, subscription_id=sid, status=status or ("paid" if paid_on else "open"),
                        amount_due=str(amount), amount_paid=str(amount if paid_on else 0), currency="USD",
                        issued_on=issued_on, due_on=due_on, paid_on=paid_on, description=description)

    def payment(self, invoice, pid, status, attempted_on, method, failure_code="", description=""):
        return self.add("billing/payments", source_id=pid, invoice_id=invoice["source_id"],
                        customer_id=invoice["customer_id"], account_key=invoice["account_key"],
                        amount=invoice["amount_due"], currency=invoice["currency"], status=status,
                        attempted_on=attempted_on, method=method, failure_code=failure_code, refunded="no",
                        disputed="no", description=description)


def silent_escalation(b):
    key = "northwind-traders.example"
    email = b.company(key, "Northwind Traders", "Jenna Lopez", "Wholesale Distribution", "Seattle", "WA",
                      "United States", "+1-206-555-0140", "2025-02-10",
                      "Ops team loves the platform. Keen to roll it out to the Portland warehouse next.",
                      "Laura Callahan", "Head of Operations")
    deal = b.deal(key, email, "Northwind - Warehouse Expansion", "Contract Sent", "open", 64000, 0.9,
                  "2026-07-31", "Jenna Lopez", "2026-05-04", "2026-06-12",
                  "Champion confirmed budget. Expansion looks very likely - paperwork goes out this week.",
                  kind="New Business", priority="high")
    b.note(key, "Jenna Lopez", "2026-06-12", "Great call with Laura. They want Portland live before Q4 "
           "peak season and see us as the obvious choice. Expansion is all but done.", deal["source_id"])
    b.case(key, "Northwind Traders", email, "Laura Callahan",
           "Nightly export failing - we cannot close the month", "open", "urgent", "bug", "area:export",
           "2026-06-19", "2026-06-25", 0,
           "This is the third time I have written about this. Our nightly export has failed every night "
           "since your last upgrade and our finance team cannot close the month. Nobody has replied to a "
           "single message. I am frankly angry - if this is not fixed by Friday I will be recommending to "
           "our leadership that we stop the expansion and look at other vendors.")
    cid, sid = "cus_Northwind0018", "sub_Northwind0022"
    b.biller(key, cid, "Northwind Traders", f"accounts@{key}", "card_visa_5521", "2025-03-01")
    b.subscription(key, cid, sid, "Platform - Business", "price_biz_annual_48k", 48000, "year", 50,
                   "2025-03-01", "2026-03-01", "2027-03-01")
    for year, paid in [("2025", "2025-03-12"), ("2026", "2026-03-11")]:
        i = b.invoice(key, cid, f"in_northwind_{year}_001", sid, 48000, f"{year}-03-01", f"{year}-03-31", paid,
                      f"Year {int(year) - 2024} - Platform Business (50 seats)")
        b.payment(i, f"ch_northwind_{year}_001", "succeeded", paid, "card", description=f"Northwind {year}")
    b.arc("silent escalation", key, "AtRiskAccount (urgent case, pipeline into trouble); HealthCrmAwareness unaware")


def quiet_churner(b):
    key = "chumbucket.com"
    deal = one(b.t["crm/opportunities"], account_key=key, title="Chum Bucket - Renewal")
    deal.update(probability="0.9", close_on="2026-07-10", modified_on="2026-06-20",
                note="Renewal on track. Ariana says sign-off is a formality. Forecast to close in July.")
    invoice = one(b.t["billing/invoices"], source_id="in_chumbucket_2026_001")
    assert invoice["status"] == "open" and invoice["due_on"] == "2026-06-04"
    for n, (day, code) in enumerate([("2026-06-04", "card_declined"), ("2026-06-11", "insufficient_funds"),
                                     ("2026-06-18", "card_declined")], 1):
        b.payment(invoice, f"ch_chumbucket_2026_00{n}f", "failed", day, "card", code,
                  f"Chum Bucket renewal - attempt {n} failed")
    customer = one(b.t["billing/customers"], account_key=key)
    customer.update(delinquent="yes", balance_owed=invoice["amount_due"])
    b.arc("quiet churner", key, "AtRiskAccount (riskFailedPayments 1)",
          "any support case; any CRM note about payment")


def withholding(b):
    key = "contoso.example"
    email = b.company(key, "Contoso Ltd", "Sophie Turner", "Professional Services", "Chicago", "IL",
                      "United States", "+1-312-555-0175", "2024-05-20",
                      "Steady account. Annual renewal each June; finance runs procurement.",
                      "Marcus Webb", "Finance Director")
    b.deal(key, email, "Contoso - Annual Renewal", "Closed Won", "won", 86000, 1, "2026-05-20",
           "Sophie Turner", "2026-04-01", "2026-05-20", "Renewed on the same terms.")
    cid, sid = "cus_Contoso000019", "sub_Contoso000023"
    b.biller(key, cid, "Contoso Ltd", f"ap@{key}", "wire_transfer", "2024-06-01")
    b.subscription(key, cid, sid, "Platform - Enterprise", "price_ent_annual_86k", 86000, "year", 100,
                   "2024-06-01", "2026-06-01", "2027-06-01")
    paid = b.invoice(key, cid, "in_contoso_2025_001", sid, 86000, "2025-05-27", "2025-06-10", "2025-06-06",
                     "Year 2 - Platform Enterprise (100 seats)")
    b.payment(paid, "py_contoso_2025_001", "succeeded", "2025-06-06", "ach_credit_transfer",
              description="Contoso Year 2 wire")
    unpaid = b.invoice(key, cid, "in_contoso_2026_001", sid, 86000, "2026-05-27", "2026-06-10", "",
                       "Year 3 - Platform Enterprise (100 seats)")
    case = b.case(key, "Contoso Ltd", email, "Marcus Webb", "CSV export silently drops rows over 10,000",
                  "open", "high", "bug", "area:export", "2026-06-02", "2026-06-24", 4,
                  "Our month-end CSV export stops at 10,000 rows without any warning, so every report we send "
                  "the board has been wrong. We need a fix, not a workaround. To be clear: we will not pay "
                  "the June invoice until the export is fixed.")
    assert case["opened_on"] <= unpaid["due_on"]
    b.arc("withholding", key, f"POSSIBLY_WITHHELD_OVER {unpaid['number']} -> case {case['source_id']}")


def acknowledged_trouble(b):
    key = "initech.com"
    account = one(b.t["crm/accounts"], account_key=key)
    account.update(relationship="customer",
                   note="SMB software shop, switched from a competitor in March. Price-sensitive; Emily is the champion.")
    deal = one(b.t["crm/opportunities"], account_key=key, title="Initech - Starter Package")
    deal.update(stage="Closed Won", stage_order="", status="won", probability="1", close_on="2026-03-10",
                modified_on="2026-03-10", note="Signed monthly to start; annual once they are settled.")
    email, person = "emily.r@initech.com", "Emily Rodriguez"
    cid, sid = "cus_Initech00020", "sub_Initech000024"
    b.biller(key, cid, "Initech LLC", "billing@initech.com", "ach_bank_7731", "2026-03-10")
    b.subscription(key, cid, sid, "Platform - Starter", "price_starter_monthly_1550", 1550, "month", 15,
                   "2026-03-10", "2026-06-10", "2026-07-10")
    for month in ["03", "04", "05", "06"]:
        paid_on = {"03": "2026-03-20", "04": "2026-04-21"}.get(month, "")
        i = b.invoice(key, cid, f"in_initech_2026_0{month}", sid, 1550, f"2026-{month}-10", f"2026-{month}-25",
                      paid_on, f"Platform Starter (15 seats) - 2026-{month}")
        if paid_on:
            b.payment(i, f"py_initech_2026_0{month}", "succeeded", paid_on, "ach_credit_transfer",
                      description=f"Initech 2026-{month}")
    export = b.case(key, "Initech LLC", email, person, "Scheduled export times out for large workspaces",
                    "open", "high", "bug", "area:export", "2026-05-18", "2026-06-23", 6,
                    "Our scheduled export times out on our largest workspace, so the weekly report to our "
                    "customers has not gone out for two weeks. Smaller workspaces are fine.")
    ui = b.case(key, "Initech LLC", email, person, "Dashboard filters reset after page refresh", "open",
                "medium", "bug", "area:ui", "2026-06-08", "2026-06-19", 3,
                "Every time we refresh the dashboard the filters go back to the defaults. Annoying more than "
                "anything, but the team keeps getting caught by it.")
    deal_id = deal["source_id"]
    b.note(key, "Mike Davis", "2026-05-20",
           "Emily called: their scheduled export times out on the big workspace, which is why May's invoice "
           "is late. Told her engineering has the export timeout; she will pay once the export runs.", deal_id)
    b.note(key, "Mike Davis", "2026-06-09",
           "Follow-up with Emily. The export timeout is still open, and now dashboard filters reset when "
           "they refresh the page. Patient, but wants a date. Holding off chasing the overdue invoices "
           "until we have a fix date for the export.")
    # Picked up, not just noted: the owner scheduled the work, which is what a duty that keeps every
    # at-risk account acknowledged looks for. A note says somebody knew; a follow-up says somebody
    # will do something by a date.
    # Due after the as-of date, so it reads as work in hand rather than as one of Mike's past-due tasks.
    b.followup(key, "Mike Davis", "2026-06-09", "2026-07-03", "Get a fix date for Initech's export timeout",
               "Emily is waiting on a date before May and June are paid; chase engineering for it.")
    b.arc("acknowledged trouble", key,
          f"AtRiskAccount; HealthCrmAwareness aware (cases {export['source_id']}, {ui['source_id']}); a follow-up scheduled",
          "HealthCrmAwareness unaware; StewardUnacknowledgedRisk")


def failed_payments(b):
    key = "acmecorp.com"
    cid = one(b.t["billing/customers"], account_key=key)["source_id"]
    i = b.invoice(key, cid, "in_acme_2026_emea", "", 18000, "2026-05-15", "2026-06-14", "",
                  "EMEA onboarding services (one-off)")
    b.payment(i, "ch_acme_2026_emea_a", "failed", "2026-06-14", "card", "card_declined",
              "EMEA onboarding - 1st attempt failed (declined)")
    b.payment(i, "ch_acme_2026_emea_b", "failed", "2026-06-21", "card", "insufficient_funds",
              "EMEA onboarding - 2nd attempt failed (insufficient funds)")
    b.arc("failed payments", key, f"AtRiskAccount (riskFailedPayments; {i['number']})")


def good_payer_on_the_fifth(b):
    key = "wayfarer-travel.example"
    email = b.company(key, "Wayfarer Travel", "Jenna Lopez", "Travel", "Denver", "CO", "United States",
                      "+1-720-555-0190", "2025-06-10", "Small agency, monthly plan. Pays like clockwork.",
                      "Tom Harlow", "Owner")
    b.deal(key, email, "Wayfarer - Platform Monthly", "Closed Won", "won", 28800, 1, "2025-06-20",
           "Jenna Lopez", "2025-06-10", "2025-06-20", "Monthly plan, card on file.", kind="New Business")
    cid, sid = "cus_Wayfarer00021", "sub_Wayfarer00025"
    b.biller(key, cid, "Wayfarer Travel", f"tom.harlow@{key}", "card_visa_6610", "2025-06-20")
    b.subscription(key, cid, sid, "Platform - Starter", "price_starter_monthly_2400", 2400, "month", 12,
                   "2025-07-01", "2026-06-01", "2026-07-01")
    month = date(2025, 7, 1)
    while month <= date(2026, 6, 1):
        tag = month.strftime("%Y_%m")
        paid_on = month.replace(day=5)
        i = b.invoice(key, cid, f"in_wayfarer_{tag}", sid, 2400, (month - timedelta(days=10)).isoformat(),
                      month.isoformat(), "", f"Platform Starter (12 seats) - {month:%B %Y}")
        if month == date(2026, 3, 1):
            b.payment(i, f"ch_wayfarer_{tag}_f", "failed", paid_on.isoformat(), "card", "expired_card",
                      "Card on file expired; customer updated it the next day")
            paid_on += timedelta(days=1)
        b.payment(i, f"ch_wayfarer_{tag}", "succeeded", paid_on.isoformat(), "card",
                  description=f"Wayfarer {month:%B %Y}")
        i.update(status="paid", amount_paid=i["amount_due"], paid_on=paid_on.isoformat())
        month = (month + timedelta(days=32)).replace(day=1)
    b.arc("good payer on the 5th", key, "nothing", "AtRiskAccount; any open invoice")


def stale_deal(b):
    deal = one(b.t["crm/opportunities"], title="Globex - Enterprise Implementation")
    assert deal["status"] == "open" and deal["modified_on"] <= "2026-04-30"
    b.arc("stale deal", "globex.io", f"open deal {deal['source_id']}, untouched since {deal['modified_on']}")


def noisy_but_healthy(b):
    key = "brightline-analytics.example"
    email = b.company(key, "Brightline Analytics", "Sophie Turner", "Information Technology", "Boston", "MA",
                      "United States", "+1-617-555-0122", "2024-09-01",
                      "Power users and big fans. They file everything they find, which is a gift.",
                      "Priya Raman", "Analytics Lead")
    b.deal(key, email, "Brightline - Renewal", "Closed Won", "won", 54000, 1, "2025-09-01", "Sophie Turner",
           "2025-07-15", "2025-09-01", "Renewed early, added seats.")
    subjects = [("Tooltip overlaps the legend on narrow charts", "area:ui"),
                ("Typo in the export settings dialog", "area:export"),
                ("How do I share a dashboard read-only?", "area:org"),
                ("API pagination docs show the wrong default page size", "area:docs"),
                ("Dark mode: table borders hard to see", "area:ui"),
                ("Saved search loses its sort order", "area:search"),
                ("Can webhooks include the previous value?", "area:webhooks"),
                ("Timezone label wrong on scheduled reports", "area:reporting"),
                ("Keyboard shortcut list is out of date", "area:docs")]
    for n, (subject, label) in enumerate(subjects):
        opened = date(2026, 2, 2) + timedelta(days=13 * n)
        closed = opened + timedelta(days=1 + n % 2)
        b.case(key, "Brightline Analytics", email, "Priya Raman", subject, "resolved", "low",
               "question" if subject.endswith("?") else "bug", label, opened.isoformat(), closed.isoformat(),
               2 + n % 3, f"{subject}. Small thing, thanks as always for the quick turnaround!",
               closed_on=closed.isoformat())
    cid, sid = "cus_Brightline022", "sub_Brightline026"
    b.biller(key, cid, "Brightline Analytics", f"finance@{key}", "card_amex_3301", "2024-09-01")
    b.subscription(key, cid, sid, "Platform - Business", "price_biz_annual_54k", 54000, "year", 60,
                   "2024-09-01", "2025-09-01", "2026-09-01")
    for year, paid in [("2024", "2024-09-10"), ("2025", "2025-09-08")]:
        i = b.invoice(key, cid, f"in_brightline_{year}_001", sid, 54000, f"{year}-09-01", f"{year}-10-01", paid,
                      f"Platform Business (60 seats) - {year}")
        b.payment(i, f"ch_brightline_{year}_001", "succeeded", paid, "card", description=f"Brightline {year}")
    b.arc("noisy but healthy", key, "nothing", "AtRiskAccount; HealthCaseTriage (no open case)")


def writes_sandbox(b):
    """The one account a harness may write to: add notes and tasks, move its deal. It carries no
    story, so a write there cannot change any other arc's answer."""
    key = SANDBOX
    email = b.company(key, "Fernhollow Supply Co", "Mike Davis", "Professional Services", "Austin", "TX",
                      "United States", "+1-512-555-0150", "2026-05-04",
                      "Regional office-supply distributor. Small purchasing team, new to us this spring.",
                      "Sam Ortega", "Operations Manager")
    deal = b.deal(key, email, "Fernhollow - Pilot", "Qualified to Buy", "open", 10000, 0.4, "2026-09-30",
                  "Mike Davis", "2026-05-04", "2026-05-04", "Pilot for the purchasing team. Budget set aside for a "
                  "small first phase.", kind="New Business")
    b.arc("writes sandbox", key, f"the only account a harness writes to (deal {deal['source_id']})",
          "any write to another account")


def manual_dunning(b, exclude):
    """An AR clerk writes a note the day after every failed card, which is the habit a Chaser is
    later asked to take over. The failures are added BEFORE an invoice's successful payment, so
    every invoice still ends paid and no rule changes its mind about the account.

    Lago holds a payment as an invoice metadata pair, and an invoice holds at most five pairs, two
    of them taken: so an invoice carries at most three attempts here, the success included."""
    refunded = {r["payment_id"] for r in read(b.root, "billing/refunds.csv")}
    disputed = {r["payment_id"] for r in read(b.root, "billing/disputes.csv")}
    crm = {a["account_key"]: a for a in b.t["crm/accounts"]}
    names = {c["source_id"]: c["email"] for c in b.t["billing/customers"]}
    attempts = {}
    for p in b.t["billing/payments"]:
        attempts.setdefault(p["invoice_id"], []).append(p)
    eligible = [i for i in b.t["billing/invoices"]
                if i["status"] == "paid" and i["account_key"] in crm and i["account_key"] not in exclude
                and len(attempts.get(i["source_id"], [])) == 1
                and attempts[i["source_id"]][0]["method"] in FAILURES
                and not {p["source_id"] for p in attempts[i["source_id"]]} & (refunded | disputed)]
    for n, i in enumerate(sorted(eligible, key=lambda r: r["source_id"])):
        paid = attempts[i["source_id"]][0]
        codes = FAILURES[paid["method"]]
        tries = [d(paid["attempted_on"]) - timedelta(days=gap) for gap in (6, 3)]
        tries = [t for t in tries if t > d(i["issued_on"])]
        for k, when in enumerate(tries):
            code = codes[(n + k) % len(codes)]
            b.payment(i, f"{paid['source_id']}_f{k + 1}", "failed", when.isoformat(), paid["method"], code,
                      f"{i['number']} - attempt failed ({code.replace('_', ' ')})")
            retry = "retrying in three days" if k + 1 < len(tries) else "the retry is due on " + \
                (when + timedelta(days=3)).isoformat()
            b.note(i["account_key"], AR_CLERK, (when + timedelta(days=1)).isoformat(),
                   f"Payment for {i['number']} ({i['currency']} {int(float(i['amount_due'])):,}) failed "
                   f"yesterday: {code.replace('_', ' ')}. Emailed {names[i['customer_id']]} to ask them to "
                   f"check the {paid['method'].replace('_', ' ')} details; {retry}.")
    # Wayfarer's one expired card was handled the same way.
    b.note("wayfarer-travel.example", AR_CLERK, "2026-03-06",
           "Card for Wayfarer's March invoice expired. Tom updated it within the hour and the retry went "
           "through today. Nothing to chase - they always pay on the 5th.")
    b.arc("manual dunning", "*", f"{sum(1 for x in b.notes if x['author'] == AR_CLERK)} notes by {AR_CLERK}, "
          "each the day after a failed payment")


def monday_calls(b):
    """Every Monday for twelve weeks, Mike Davis ran the overdue list and, on the Mondays it was not
    empty, booked a call that week with each account on it — the second habit an agent is later
    asked to learn. The list is computed from the invoices as they stood THAT Monday, not as they
    stand now."""
    crm = {a["account_key"]: a for a in b.t["crm/accounts"]}
    people = {}
    for c in b.t["crm/contacts"]:
        people.setdefault(c["account_key"], c["email"])
    monday = date(2026, 6, 22)
    weeks = [monday - timedelta(weeks=w) for w in range(11, -1, -1)]
    for m in weeks:
        overdue = sorted({i["account_key"] for i in b.t["billing/invoices"]
                          if i["account_key"] in crm and i["status"] != "uncollectible"
                          and d(i["due_on"]) < m and (not i["paid_on"] or d(i["paid_on"]) > m)
                          and d(i["issued_on"]) <= m})
        for slot, key in enumerate(overdue):
            start = f"{m + timedelta(days=2)} {14 + slot // 2:02d}:{30 * (slot % 2):02d}:00"
            b.meetings.append({"source_id": f"meeting-{len(b.meetings) + 1:04d}", "account_key": key,
                               "title": f"Overdue invoice check-in: {crm[key]['name']}",
                               "organizer": "Mike Davis", "attendee_email": people.get(key, ""),
                               "booked_on": m.isoformat(), "starts_at": start, "minutes": "30"})
    booked = len({m["booked_on"] for m in b.meetings})
    b.arc("monday calls", "*", f"{len(b.meetings)} calls booked by Mike Davis on {booked} distinct Mondays, "
          f"out of {len(weeks)} Mondays checked")


def assert_controls(b):
    for key in CONTROLS:
        assert not [c for c in b.t["support/cases"] if c["account_key"] == key and c["status"] == "open"], key
        assert not [i for i in b.t["billing/invoices"] if i["account_key"] == key and i["status"] != "paid"], key
        assert not [p for p in b.t["billing/payments"] if p["account_key"] == key and p["status"] == "failed"], key
        b.arc("control", key, "nothing", "AtRiskAccount; any open case; any failed payment")


def assert_shared_incident(b):
    keys = {c["account_key"] for c in b.t["support/cases"]
            if c["status"] == "open" and "area:export" in c["labels"].split(",")}
    story = {"northwind-traders.example", "contoso.example", "initech.com"}
    assert story <= keys, keys
    b.arc("shared incident", ",".join(sorted(story)), "SHARES_ISSUE pairwise on area:export")


def apply(root):
    b = Book(root)
    for arc in (silent_escalation, quiet_churner, withholding, acknowledged_trouble, failed_payments,
                good_payer_on_the_fifth, stale_deal, noisy_but_healthy, writes_sandbox):
        arc(b)
    story = {a["account_key"] for a in b.arcs}
    manual_dunning(b, story | set(CONTROLS) | {"bluth.com"})
    monday_calls(b)
    assert_shared_incident(b)
    assert_controls(b)
    b.arc("group contagion", "", "NOT SEEDED: the book has no parent/subsidiary links")

    keys = [a["account_key"] for a in b.t["crm/accounts"]]
    assert len(keys) == len(set(keys)), "account_key is the spine: two accounts would merge"
    for table in ("billing/invoices", "billing/payments", "support/cases"):
        ids = [r["source_id"] for r in b.t[table]]
        assert len(ids) == len(set(ids)), f"duplicate source_id in {table}"
    per_invoice = {}
    for p in b.t["billing/payments"]:
        per_invoice[p["invoice_id"]] = per_invoice.get(p["invoice_id"], 0) + 1
    assert max(per_invoice.values()) <= 3, "Lago holds at most three attempts per invoice"
    assert sum(1 for x in b.notes if x["author"] == AR_CLERK) >= 30, "step 5 needs thirty-plus dunning notes"

    counts = {name: write(root, name + ".csv", rows) for name, rows in b.t.items()}
    counts["crm/notes"] = write(root, "crm/notes.csv", b.notes)
    counts["crm/meetings"] = write(root, "crm/meetings.csv", b.meetings)
    counts["crm/followups"] = write(root, "crm/followups.csv", b.followups)
    counts["arcs"] = write(root, "arcs.csv", b.arcs)
    return counts
