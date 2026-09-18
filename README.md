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

Read the CSVs, not the workbooks. Pin a tag, not `main`: a data edit must not be able to
change a demo's answers silently.

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

    python3 convert.py

It rewrites `csv/` and exits non-zero if the datasets stopped agreeing — a billing customer
pointing at a missing company, an issue from an unknown contact, a deals total that no
longer matches its rows. Review the CSV diff, commit both, tag.

Needs Python 3 and `openpyxl`.
