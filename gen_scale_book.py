#!/usr/bin/env python3
"""
Generate a SCALE book that reads like a real one.

Why this exists. `book-2000` gave the estate 2,000 accounts named `Account 00000`, contacts
named `First00000 Last00000`, and one note repeated two thousand times: "Generated account N
for scale measurement." It did its job — the scale found four real bugs — and it made the
demo unusable and two of its headline views meaningless:

  * `HealthCrmAwareness` asks a model whether anything sales wrote touches the topic of the
    customer's open case. Against "Generated account 1976 for scale measurement" the only
    honest answer is `unaware`, for every account, forever. A judgement view over filler
    text is not a judgement view.
  * `HealthCaseTriage` reads the customer's own words for IMPACT and MOOD. "Generated case
    body for Account 00000" has neither.
  * `HealthSharedIssues` pairs accounts by shared product area, which lives in the case's
    `labels`. `book-2000` wrote none.

So the bar here is not "plausible names". It is THE DATA MUST CONTAIN THE SIGNAL THE VIEWS
LOOK FOR, in a known mixture, so a demo shows a spread rather than a constant — and so the
harness can assert proportions instead of hoping.

What is deliberately mixed, and roughly how much:

  awareness   ~30% of accounts with an open case get a note that genuinely names the case's
              product area, so `HealthCrmAwareness` returns both verdicts. The rest write
              about renewals, expansion and procurement, like real CRM notes.
  triage      cases are drawn across impact (blocked / degraded / inconvenienced / asking)
              and mood (frustrated / neutral / positive) so triage returns a spread.
  areas       a small fixed vocabulary of product areas, so accounts genuinely SHARE issues
              and `HealthSharedIssues` has pairs to find.
  billing     ~2/3 of accounts are billed; of those a slice is unpaid and a smaller slice
              FAILED, so receivables and the at-risk rules have something to conclude.

Determinism: one seed, fixed lists, no wall-clock. Re-running produces byte-identical CSVs,
because a demo whose answers move when nobody changed anything cannot be reconciled.

  python3 gen_scale_book.py --out ~/embabel/books/book-scale --count 2000
"""
import argparse, csv, json, os, random, unicodedata
from datetime import date, timedelta

SEED = 20260921
# `account_key` IS THE SPINE KEY every realm joins on, so the domain must be unique per
# account. The first cut of this generator derived the slug from the name WITHOUT its
# suffix and produced 1,018 distinct domains for 2,000 companies — which does not fail,
# it silently MERGES accounts into one another. Uniqueness is asserted at the end.
FIRST = ["Sarah","Michael","Priya","Tomas","Aisha","Daniel","Mei","Lucas","Hannah","Omar","Elena","Jacob","Fatima","Noah","Ingrid","Rafael","Yuki","Grace","Andre","Leila","Peter","Nadia","Samuel","Clara","Dmitri","Rosa","Ethan","Amara","Viktor","Chloe","Hassan","Maya","Oscar","Ruth","Felix","Nora","Marcus","Zara","Ivan","Tessa"]
LAST  = ["Chen","Okafor","Nowak","Lindqvist","Rahman","Weber","Silva","Kowalski","Moreau","Tanaka","Bauer","Ferreira","Nakamura","Dubois","Haddad","Novak","Iversen","Mbeki","Costa","Varga","Schmidt","Lombardi","Petrov","Andersen","Reyes","Fischer","Duarte","Kaur","Jansen","Bergman","Adeyemi","Marchetti","Sorensen","Kovacs","Delgado","Nilsson","Barros","Meier","Larsen","Ortiz"]
A = ["North","Cedar","Harbor","Vertex","Lumen","Iron","Quill","Basalt","Meridian","Alder","Kestrel","Onyx","Pallas","Thornton","Vantage","Briar","Halcyon","Sable","Cobalt","Larkin","Ridge","Solace","Tessera","Umber","Wexford","Ashby","Bramble","Copper","Drummond","Elmwood","Fairlight","Granite","Hollis","Inverness","Juniper","Kelvin","Loxley","Marlowe","Newlyn","Orrery"]
B = ["Foundry","Analytics","Logistics","Systems","Robotics","Dynamics","Labs","Works","Partners","Group","Medical","Biosciences","Freight","Energy","Interactive","Networks","Materials","Instruments","Studios","Capital","Agritech","Optics","Marine","Aerospace","Textiles","Brewing","Automotive","Ceramics","Diagnostics","Packaging"]
SUF = ["","","","","Ltd","Inc","GmbH","Holdings","Group","AB","SA","Pty"]
INDUSTRY = ["Manufacturing","Information Technology","Logistics","Healthcare","Financial Services","Energy","Retail","Media","Agriculture","Professional Services"]
CITIES = [("San Francisco","CA","United States","+1-415-555-%04d"),("New York","NY","United States","+1-212-555-%04d"),("Austin","TX","United States","+1-512-555-%04d"),("London","","United Kingdom","+44-20-7946-%04d"),("Berlin","BE","Germany","+49-30-5550-%04d"),("Toronto","ON","Canada","+1-416-555-%04d"),("Sydney","NSW","Australia","+61-2-5550-%04d"),("Dublin","","Ireland","+353-1-555-%04d"),("Singapore","","Singapore","+65-6555-%04d"),("Stockholm","","Sweden","+46-8-555-%04d")]
OWNERS = ["Mike Davis","Jenna Lopez","Sarah Chen","Tom Alvarez","Priya Nair","Daniel Okoro"]
TITLES = ["Operations Lead","Head of Engineering","IT Director","VP Finance","Platform Architect","Support Manager","CTO","Procurement Lead","Data Engineer","Head of Security"]

# The product areas. A SMALL fixed set on purpose: accounts must genuinely share issues or
# `HealthSharedIssues` has no pairs to find, which is the whole question it answers
# ("is this one unhappy customer, or an incident?").
AREAS = [
    ("auth",      "SSO and sign-in"),
    ("billing",   "invoicing and payments"),
    ("api",       "the public API"),
    ("reporting", "reports and exports"),
    ("perf",      "platform performance"),
    ("data",      "data import and sync"),
    ("mobile",    "the mobile app"),
    ("search",    "search and indexing"),
]
# subject, body, impact, mood, kind. The body is the CUSTOMER'S OWN WORDS, with a specific
# in it, because that is what `HealthCaseTriage` reads to judge impact and mood. A 40-reply
# thread about a feature request is not trouble; a 6-reply thread from a blocked customer is.
CASE_SHAPES = {
 "auth": [
  ("SSO login loop after password reset","Users who reset their password are caught in a redirect loop back to the IdP. Roughly 40 of our staff cannot sign in at all this morning. We need this fixed today.","blocked","frustrated","problem"),
  ("SAML session timeout ignores our IdP setting","Sessions expire at 15 minutes although our IdP is set to 60. People are re-authenticating all day. Not blocking, but it is wearing everyone down.","degraded","frustrated","bug"),
  ("Can we enforce MFA per group?","We would like MFA required for the finance group only. Is that configurable today, or on the roadmap?","asking","neutral","question"),
 ],
 "billing": [
  ("Invoice shows the wrong currency","Our March invoice came through in USD but our contract is in GBP. Finance cannot process it until it is reissued.","blocked","neutral","problem"),
  ("Card charged twice for the same period","We were billed twice on the 3rd. Please refund the duplicate — it has already cleared.","degraded","frustrated","problem"),
  ("Purchase order number on invoices","Can you add our PO number to the invoice header? Our AP system rejects invoices without it.","asking","neutral","question"),
 ],
 "api": [
  ("429s on the bulk endpoint well under our documented limit","We are being rate limited at roughly 60 requests a minute against a documented 600. Our nightly sync has not completed for three days.","blocked","frustrated","bug"),
  ("Webhook retries arrive out of order","Retried webhooks arrive after newer events, so our state goes backwards. We can work around it, but it is fragile.","degraded","neutral","bug"),
  ("Is there a sandbox for the v3 API?","We would like to test the v3 migration without touching production data.","asking","positive","question"),
 ],
 "reporting": [
  ("Scheduled report has not arrived since the 3rd","The Monday exec report stopped arriving. Nothing changed our side. The board meeting is Thursday.","blocked","frustrated","problem"),
  ("CSV export truncates at 10,000 rows","Exports silently stop at 10k rows — no warning, so we published a partial number last month before noticing.","degraded","frustrated","bug"),
  ("Custom report builder","Is a custom report builder on the roadmap? We are rebuilding several by hand each month.","asking","neutral","question"),
 ],
 "perf": [
  ("Dashboard takes over 40 seconds to load","The main dashboard has gone from instant to 40+ seconds since last week. Our floor staff have stopped using it.","degraded","frustrated","problem"),
  ("Timeouts during the 9am peak","Every morning between 9 and 10 we see timeouts. It clears by mid-morning.","degraded","neutral","problem"),
  ("Guidance on sizing for 500 concurrent users","We are scaling to about 500 concurrent users next quarter. Any sizing guidance?","asking","positive","question"),
 ],
 "data": [
  ("Nightly sync silently dropping records","About 2% of records vanish in the nightly sync with no error logged. We only found it by reconciling by hand.","blocked","frustrated","bug"),
  ("Duplicate records after the last import","The last import created duplicates for anything with an apostrophe in the name.","degraded","neutral","bug"),
  ("Field mapping for custom attributes","How do we map our custom attributes on import? The docs stop short of this.","asking","neutral","question"),
 ],
 "mobile": [
  ("App crashes on launch after the latest update","Since the update the app closes immediately on launch for our Android users. Our field team is entirely mobile.","blocked","frustrated","problem"),
  ("Offline mode loses edits","Edits made offline are lost when the app reconnects. Staff are keeping paper notes as a backup.","degraded","frustrated","bug"),
  ("Is tablet layout planned?","The phone layout works on tablets but wastes a lot of space. Anything planned?","asking","positive","question"),
 ],
 "search": [
  ("Search returns nothing for exact record names","Searching an exact record name returns no results; browsing finds it fine. Staff cannot find anything.","blocked","frustrated","bug"),
  ("Index lags about an hour behind","New records take roughly an hour to appear in search. Manageable, but confusing for new staff.","degraded","neutral","problem"),
  ("Can we boost certain fields in search?","We would like matches on reference number to rank above description matches.","asking","neutral","question"),
 ],
}
# CRM notes that say nothing about support — what most real notes look like.
NEUTRAL_NOTES = [
 "{industry} firm in {city}. Renewal due next quarter; no blockers flagged by the account team.",
 "Expanding headcount in {city} this year. Watching seat count against the current plan.",
 "Multi-stakeholder evaluation. Procurement is the long pole, not the product.",
 "Steady account since {year}. Low touch, pays on time, no escalations to date.",
 "Moved from annual to monthly billing at their request in {year}.",
 "Strategic account for the {industry} vertical. Exec sponsor engaged.",
 "Growing fast post-funding. Likely upsell conversation in the next two quarters.",
 "Consolidating vendors this year; we are the incumbent in this category.",
]
# Notes that DO touch the case's area — the `aware` half of the awareness judgement.
AWARE_NOTES = [
 "Champion raised {area_h} problems on the last call; engineering is aware and a fix is in flight.",
 "Ongoing frustration with {area_h}. Flagged to the account team before the renewal conversation.",
 "They escalated {area_h} to their exec sponsor. Handle the renewal carefully until it is closed out.",
 "Known issue with {area_h} on this account; we agreed a weekly check-in until it is resolved.",
]
DEAL_KINDS = [("New Business","Platform Licence"),("Upsell","Additional Seats"),("Renewal","Annual Renewal"),("New Business","Enterprise Tier"),("Upsell","Premium Support")]
STAGES = [("Qualification",1,0.2),("Discovery",2,0.35),("Proposal",3,0.55),("Negotiation",4,0.75),("Closed Won",5,1.0),("Closed Lost",5,0.0)]

def book_header(name):
    """The hand-authored book's header for `name`, so both books share one format."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "book", name), newline="") as fh:
        return next(csv.reader(fh))

def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=2000)
    ap.add_argument("--start-id", type=int, default=200000,
                    help="Base for source ids; keep clear of the hand-authored book's (101-1400).")
    args = ap.parse_args()
    rng = random.Random(SEED)
    N = args.count
    # A FIXED today, not `date.today()`: a book whose answers drift with the wall clock
    # cannot be reconciled twice. Every date below is placed RELATIVE to it, and the past
    # ones must actually be in the past — the first cut let `created_on` run to 2027-08 and
    # wrote notes like "moved to monthly billing in 2027", while invoices were ISSUED in the
    # future, so nothing was overdue and receivables had nothing to report.
    TODAY = date(2026, 9, 21)
    base = date(2025, 1, 6)
    span = (TODAY - base).days - 30          # newest account is ~a month old

    # ---- names, unique by construction ----
    names, seen = [], set()
    while len(names) < N:
        n = (f"{rng.choice(A)} {rng.choice(B)} {rng.choice(SUF)}").strip()
        if n in seen: continue
        seen.add(n); names.append(n)

    accounts, contacts, opps, cases = [], [], [], []
    bcust, binv, bsub, bpay = [], [], [], []

    for i, name in enumerate(names):
        # `.example.com`, like the hand-authored book: CRMs reject contact emails on the `.example` TLD.
        key = f"{slug(name)}.example.com"
        city, region, country, phfmt = CITIES[i % len(CITIES)]
        industry = INDUSTRY[i % len(INDUSTRY)]
        owner = OWNERS[i % len(OWNERS)]
        created = base + timedelta(days=rng.randint(0, span))
        # A third of the book has an open case; that is the population every "who is in
        # trouble" view reports on, and it must not be everybody or the answer is noise.
        has_case = (i % 3 == 0)
        area, area_h = AREAS[i % len(AREAS)]
        # ~30% of troubled accounts have a note that names the area -> a real mix of verdicts.
        aware = has_case and (i % 10) < 3
        if aware:
            note = rng.choice(AWARE_NOTES).format(area_h=area_h)
        else:
            note = rng.choice(NEUTRAL_NOTES).format(industry=industry, city=city, year=created.year)

        accounts.append(dict(account_key=key, name=name, website=f"https://www.{key}",
            phone=phfmt % (i % 10000), industry=industry, city=city, region=region, country=country,
            owner=owner, relationship="customer" if i % 4 else "prospect",
            annual_revenue=1_000_000 + (i * 7919) % 90_000_000, employees=10 + (i * 37) % 4000,
            created_on=created.isoformat(), note=note, source_id=args.start_id + i))

        fn, ln = FIRST[i % len(FIRST)], LAST[(i * 7) % len(LAST)]
        email = f"{fn.lower()}.{ln.lower()}@{key}"
        contacts.append(dict(email=email, first_name=fn, last_name=ln,
            job_title=TITLES[i % len(TITLES)], phone=phfmt % ((i + 1) % 10000), account_key=key,
            owner=owner, city=city, region=region, country=country,
            created_on=created.isoformat(),
            last_activity_on=(created + timedelta(days=rng.randint(1, 300))).isoformat(),
            note=f"{TITLES[i % len(TITLES)]}; main point of contact." if i % 3 else
                 "Technical buyer. Ran the evaluation and stayed involved after go-live.",
            source_id=args.start_id + 100000 + i))

        stage, order, prob = STAGES[i % len(STAGES)]
        kind, product = DEAL_KINDS[i % len(DEAL_KINDS)]
        status = "won" if stage == "Closed Won" else ("lost" if stage == "Closed Lost" else "open")
        opps.append(dict(source_id=args.start_id + 200000 + i, title=f"{name} - {product}",
            account_key=key, contact_email=email, pipeline="Sales Pipeline", stage=stage,
            stage_order=order, status=status, amount=5000 + (i * 1237) % 295000, currency="USD",
            probability=prob, close_on=(created + timedelta(days=90)).isoformat(), owner=owner,
            priority=["low","medium","high"][i % 3], kind=kind,
            created_on=created.isoformat(), modified_on=(created + timedelta(days=30)).isoformat(),
            note=("Renewal conversation is tied to the open support issue; see the account note."
                  if aware else rng.choice([
                    "Procurement has the paperwork; no product blockers.",
                    "Champion is engaged. Competing against an incumbent.",
                    "Budget confirmed for this quarter.",
                    "Expansion driven by headcount growth."]))))

        if has_case:
            # `i // 3`, NOT `i % 3`. A case only exists when `i % 3 == 0`, so indexing the
            # shapes by `i % 3` selects [0] every single time: 667 cases, all "blocked",
            # all urgent, and `HealthCaseTriage` — whose entire job is telling a blocked
            # customer from someone asking a question — returns one answer forever. An
            # index must not be derived from the same expression that gated the branch.
            subj, body, impact, mood, ckind = CASE_SHAPES[area][(i // 3) % len(CASE_SHAPES[area])]
            # Opened after the account existed and before today, so an open case is a case
            # somebody could actually still be waiting on.
            max_age = max(1, (TODAY - created).days - 1)
            opened = created + timedelta(days=rng.randint(0, max_age))
            # Reply count tracks IMPACT, so a long thread is not automatically trouble —
            # the distinction HealthCaseTriage exists to make.
            replies = {"blocked": rng.randint(4, 12), "degraded": rng.randint(6, 30),
                       "asking": rng.randint(1, 5)}[impact]
            cases.append(dict(source_id=args.start_id + 300000 + i, subject=subj, account_key=key,
                account_name=name, requester_email=email, requester_name=f"{fn} {ln}",
                status="open", priority={"blocked":"urgent","degraded":"high","asking":"low"}[impact],
                kind=ckind, labels=f"area:{area},impact:{impact}", filed_on_behalf="no",
                filed_by=email, engineers="", milestone="", opened_on=opened.isoformat(),
                updated_on=(opened + timedelta(days=2)).isoformat(), closed_on="",
                reply_count=replies, body=body))

        # ~2/3 billed; of those, a slice unpaid and a smaller slice failed, so receivables
        # and the at-risk rules have something real to conclude.
        if i % 3 != 2:
            cid = args.start_id + 400000 + i
            amount = 100 * (1 + (i % 40))
            paystate = "failed" if i % 37 == 0 else ("pending" if i % 5 == 0 else "succeeded")
            bcust.append(dict(source_id=cid, account_key=key, name=name, email=email,
                phone=phfmt % (i % 10000), currency="USD" if i % 6 else "GBP", country=country,
                payment_method="card", delinquent=str(paystate != "succeeded").lower(),
                balance_owed=0 if paystate == "succeeded" else amount,
                created_on=created.isoformat(), known_to_crm="true",
                note="Billed monthly on the standard plan." if i % 2 else "Annual contract, invoiced monthly."))
            sid = args.start_id + 500000 + i
            bsub.append(dict(source_id=sid, customer_id=cid, account_key=key, status="active",
                product=product, plan_code="plan_std", amount=amount,
                currency="USD" if i % 6 else "GBP", interval="monthly", seats=1 + (i % 60),
                started_on=created.isoformat(),
                period_start=(TODAY - timedelta(days=15)).isoformat(),
                # Renewals spread over the next four months, so the at-risk rule's
                # 120-day renewal window catches a real subset rather than all or none.
                period_end=(TODAY + timedelta(days=1 + (i % 150))).isoformat(), canceled_on="",
                note="Renews automatically."))
            iid = args.start_id + 600000 + i
            binv.append(dict(source_id=iid, number=f"INV-{iid}", customer_id=cid, account_key=key,
                subscription_id=sid, status=paystate,
                amount_due=amount, amount_paid=amount if paystate == "succeeded" else 0,
                currency="USD" if i % 6 else "GBP",
                issued_on=(TODAY - timedelta(days=35)).isoformat(),
                # DUE IN THE PAST, so an unpaid invoice is genuinely overdue and
                # receivables/at-risk have something true to say about it.
                due_on=(TODAY - timedelta(days=5)).isoformat(),
                paid_on=(TODAY - timedelta(days=30)).isoformat() if paystate == "succeeded" else "",
                description=f"{product} — monthly licence."))
            if paystate == "succeeded":
                bpay.append(dict(source_id=args.start_id + 700000 + i, invoice_id=iid,
                    customer_id=cid, account_key=key, amount=amount,
                    currency="USD" if i % 6 else "GBP", status="succeeded",
                    paid_on=(TODAY - timedelta(days=30)).isoformat(), method="card"))

    # ---- invariants. A generator that silently produces colliding keys is worse than none:
    # the spine MERGES the rows and every per-account figure is quietly wrong. ----
    keys = [a["account_key"] for a in accounts]
    assert len(set(keys)) == len(keys) == N, f"account_key not unique: {len(set(keys))} of {N}"
    assert len(set(c["email"] for c in contacts)) == N, "contact emails not unique"
    assert all("Account " not in a["name"] for a in accounts), "a generated placeholder name survived"
    assert any("area:" in c["labels"] for c in cases), "no product areas: HealthSharedIssues has nothing to pair"
    t = TODAY.isoformat()
    assert all(a["created_on"] <= t for a in accounts), "an account was created in the future"
    assert all(c["opened_on"] <= t for c in cases), "a case was opened in the future"
    assert all(x["issued_on"] <= t for x in binv), "an invoice was issued in the future"

    out = os.path.expanduser(args.out)
    def write(sub, fname, rows, header):
        d = os.path.join(out, sub); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, fname), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=header); w.writeheader(); w.writerows(rows)
    write("crm","accounts.csv",accounts,list(accounts[0]))
    write("crm","contacts.csv",contacts,list(contacts[0]))
    write("crm","opportunities.csv",opps,list(opps[0]))
    write("support","cases.csv",cases,book_header("support/cases.csv"))
    write("billing","customers.csv",bcust,list(bcust[0]))
    write("billing","invoices.csv",binv,list(binv[0]))
    write("billing","subscriptions.csv",bsub,list(bsub[0]))
    write("billing","payments.csv",bpay,list(bpay[0]))
    write("billing","refunds.csv",[],["source_id","invoice_id","account_key","amount","currency","refunded_on","reason"])
    write("billing","disputes.csv",[],["source_id","invoice_id","account_key","amount","currency","opened_on","status","reason"])
    # The loaders read these files too; a scale book carries no history, so they are header-only.
    for name in ("emails", "calls", "notes", "meetings", "followups"):
        write("crm", f"{name}.csv", [], book_header(f"crm/{name}.csv"))
    rows = {"crm/accounts": len(accounts), "crm/contacts": len(contacts), "crm/opportunities": len(opps),
            "support/cases": len(cases), "billing/customers": len(bcust), "billing/subscriptions": len(bsub),
            "billing/invoices": len(binv), "billing/payments": len(bpay)}
    with open(os.path.join(out, "book.json"), "w") as fh:
        fh.write(json.dumps({"as_of": TODAY.isoformat(), "rows": rows}, indent=2) + "\n")

    aware_n = sum(1 for a in accounts if any(k in a["note"] for k in ("frustration","escalated","Known issue","Champion raised")))
    print(f"wrote {out}")
    print(f"  accounts {len(accounts)}  contacts {len(contacts)}  opportunities {len(opps)}")
    print(f"  cases {len(cases)}  (open, across {len(set(c['labels'] for c in cases))} area/impact combinations)")
    print(f"  billing: customers {len(bcust)} invoices {len(binv)} subs {len(bsub)} payments {len(bpay)}")
    print(f"  unpaid invoices {sum(1 for x in binv if x['status'] != 'succeeded')}"
          f" (failed {sum(1 for x in binv if x['status'] == 'failed')})")
    print(f"  accounts whose CRM note names the case area: {aware_n}")

if __name__ == "__main__":
    main()
