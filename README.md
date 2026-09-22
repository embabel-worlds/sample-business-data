# sample-business-data

One fictional B2B software company, seen through three systems that do not talk to each
other: its CRM, its billing system and its support tracker. The three datasets are linked,
so anything that joins them finds a real story — and real disagreements between them.

All of it is synthetic. No person, email, invoice or complaint here is real.

This repository belongs to no single demo. Anything that needs a CRM, a billing system and
a ticketing system with a shared customer base can load it: the products it was shaped
after (HubSpot, Stripe, GitHub Issues), or stand-ins for them (Odoo, Lago, Chatwoot, Zammad).

## Layout

| Path | What it is |
|---|---|
| `source/` | The workbooks exactly as authored in Google Sheets and downloaded as Excel. Never edited here. |
| `csv/hubspot/` | `contacts`, `companies`, `deals` — 50 each |
| `csv/stripe/` | `customers` 17, `subscriptions` 21, `invoices` 49, `charges` 48, `refunds` 5, `disputes` 3 |
| `csv/github-issues/` | `issues` 39, plus `labels_reference` and `team_reference` |
| `csv/*/README.txt` | The author's own notes from each workbook's README tab: edge cases, ID conventions, how columns map to the real APIs |
| `convert.py` | Regenerates `csv/` from `source/` and checks the three datasets agree with each other |
| `book/` | The same data with every product name taken out: `crm/`, `support/`, `billing/`, joined by `account_key`. **This is what loaders read.** |
| `to_book.py` | Regenerates `book/` from `csv/` |
| `gen_scale_book.py` | Generates a SYNTHETIC book of any size, in the same format. For measuring behaviour at scale — see below. |

Load from `book/`. Read `csv/` when you want the data as its author shaped it, and the
workbooks never. Pin a tag, not `main`: a data edit must not be able to
change a demo's answers silently.

## Scale, and why the filler has to be good

The 50 accounts here are hand-authored so that joining the three systems finds a real
story. They are not enough to show how anything behaves at size, so `gen_scale_book.py`
writes a synthetic book in the same format:

```sh
python3 gen_scale_book.py --out ~/embabel/books/book-scale --count 2000
```

It is deterministic — one seed, no wall clock — because a demo whose answers move when
nobody changed anything cannot be reconciled.

**Generated does not mean meaningless, and that is the whole point of this script.** An
earlier scale book named every company `Account 00000`, every person `First00000
Last00000`, and gave all 2,000 the note "Generated account N for scale measurement". It
found real bugs at scale, and it also made two headline views incapable of answering:
a judgement that reads CRM notes to ask "does sales know about this customer's problem"
can only ever say no against filler, and a triage that reads the customer's own words for
impact and mood has neither to read. A third view pairs accounts by shared product area,
and that book wrote no areas at all.

So this generator plants the signal the readers look for, in known proportions, and
asserts them:

| | what it plants |
|---|---|
| awareness | ~30% of troubled accounts get a note that genuinely names the case's product area, so the judgement returns BOTH verdicts |
| triage | cases spread across blocked / degraded / asking, with reply counts that track impact — so a long thread is not automatically trouble |
| areas | a small fixed area vocabulary, so accounts genuinely SHARE issues and "is this one customer or an incident?" has pairs to find |
| billing | ~2/3 billed, a slice unpaid, a smaller slice FAILED, all due in the past so overdue means overdue |

It asserts its own invariants and refuses to write a book that breaks them: `account_key`
is the spine key every realm joins on, so colliding domains do not fail, they silently
MERGE accounts — the first draft produced 1,018 distinct domains for 2,000 companies.
Dates are checked against a fixed today, after a draft dated accounts and invoices into
2027 and nothing read as overdue.

Load the two together — the hand-authored book for the story, the scale book for size.

## The book, and why it exists

`csv/` speaks HubSpot, Stripe and GitHub, because that is how the data was written. A loader
for Odoo should not need to know what a HubSpot lifecycle stage is. So `to_book.py` does
that translation once, into a vocabulary with no product in it:

| File | One row per | Notes |
|---|---|---|
| `crm/accounts.csv` | customer company | `account_key` is its domain |
| `crm/contacts.csv` | person | |
| `crm/opportunities.csv` | deal | `stage` as authored, `stage_order`, and `status`: open, won or lost |
| `support/cases.csv` | customer case | `status` open or resolved; `priority` urgent to none; `filed_on_behalf` when staff wrote it up, not the customer. The two internal engineering issues are left out |
| `billing/customers.csv` | billing customer | `known_to_crm` is `no` for the three the CRM has never heard of |
| `billing/subscriptions.csv`, `invoices.csv`, `payments.csv`, `refunds.csv`, `disputes.csv` | | a payment is one ATTEMPT, succeeded or failed |
| `book.json` | | the as-of date and the row counts |

With D datasets and P products, product-shaped loaders cost D x P. With a book in the middle
it is D + P: a new dataset writes one `to_book.py` and every loader works; a new product
writes one loader and every dataset works. Loaders exist today for Odoo, Chatwoot and Lago,
each in its realm under `seed/load_book.py`.

## How the three link

- **Company is the hub.** `hubspot/companies.csv` has a `Record ID`, a `Company Name` and a
  `Domain`. The domain is the most portable join key, because every product can hold one.
- **Billing to CRM:** `stripe/customers.csv` → `HubSpot Company ID`. Blank is deliberate:
  Hudsucker, Sirius Cybernetics and Bluth are billing customers the CRM has never heard of.
- **Support to CRM:** `github-issues/issues.csv` → `Reporter Contact (HubSpot)` and
  `Reporter Company (HubSpot)`, by name. Blank means an internal issue with no customer.
- **Inside billing:** charges → invoices → subscriptions → customers, by Stripe-style id.

## Conventions a loader needs to know

- **Money is in major units** (dollars, euros, pounds), not cents. Currency is per row.
- **`Probability` is a fraction**, 0 to 1, not a percentage.
- **Dates are ISO `YYYY-MM-DD`.** Treat **2026-06-27** as "today" for the billing and
  support data; the CRM data was written a few weeks earlier, in early May 2026. A demo
  that wants the story to stay current should turn dates into an age relative to that day.
- **Issue state is only `open` or `closed`.** In-progress is implied by assignees and a
  recent `Updated At`. Priority and type live inside the comma-separated `Labels`.
- **An issue has one `Body` and a `Comments` count**, not a thread. A product that needs
  messages gets the body as the first one.

## What the data already contains

Found by reading across the three, none of it stated in any single one:

- **Mom Corp** — 410k deal at contract sent, "CFO-approved". An open support request calls
  approval workflows a procurement-mandated requirement for that deal. The CRM is silent.
- **Wayne Enterprises** — 850k rollout at 75%, while their Slack integration has
  disconnected daily for weeks. The CRM is silent.
- **Tyrell** — 320k renewal in flight, an open performance bug and a recent regression.
- **Hooli, Arasaka** — blockers the CRM half-acknowledges. Good tests of "partly reflected".
- **Sirius Cybernetics, Bluth** — delinquent, a lost dispute and three failed card attempts,
  and absent from the CRM entirely.
- **Vandelay** — a prospect with a lost new-business deal according to the CRM; a two-year
  customer who churned with a disputed invoice according to billing.
- **Stark** — many issues, all handled, always pays. The account that should NOT be flagged.
- **The v3.3.2 regression** hit Tyrell, Stark and Acme: one incident across three accounts.

## Known quirks

Left as authored, recorded here so nobody rediscovers them:

- The workbook README tabs state 47 charges and 40 issues; the tabs hold 48 and 39.
- Charge `ch_globex_pilot_001` belongs to Acme, despite its name.
- Soylent Green Foods' domain is spelled `solyent.com`, consistently, in both contact and company.
- **Several domains belong to real businesses** (`stark.com`, `hyperion.com`, `oceanic.com`
  and others). Do not join this data to live company enrichment or news by domain: a
  fictional customer would attract a real company's headlines. Do not send email to any
  address here.
- Company names are borrowed from film and television. Weigh that before making this public.

## Updating

Edit in Google Sheets, never here. Then, per sheet: File → Download → Microsoft Excel, put
the file in `source/` under the same name, and run:

    python3 convert.py && python3 to_book.py

The first rewrites `csv/` and exits non-zero if the datasets stopped agreeing — a billing customer
pointing at a missing company, an issue from an unknown contact, a deals total that no
longer matches its rows. Review the CSV diff, commit both, tag.

Needs Python 3 and `openpyxl`.
