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
| `apply_arcs.py` | Lays the demo's story arcs over `book/`; `to_book.py` runs it after translating |
| `additions/` | CRM history the workbooks lack: more contacts, logged emails and calls, follow-ups. Drafted once, committed |
| `apply_engagements.py` | Checks `additions/` against the book, adds it, and plants the CRM signals below |
| `gen_scale_book.py` | Generates a SYNTHETIC book of any size, in the same format. For measuring behaviour at scale — see below. |

Load from `book/`. Read `csv/` when you want the data as its author shaped it, and the
workbooks never. Pin a tag, not `main`: a data edit must not be able to
change a demo's answers silently.

## Scale, and why the filler has to be good

The 55 accounts in `book/` (the workbooks' 50 plus five the arcs add) are hand-authored so
that joining the three systems finds a real story. They are not enough to show how anything
behaves at size, so `gen_scale_book.py` writes a synthetic book in the same format: domains
on `<slug>.example.com`, a `book.json` with its as-of date (2026-09-21), and the CRM history
files (`emails`, `calls`, `notes`, `meetings`, `followups`) with `book/`'s headers and no rows,
so every loader reads it as it reads `book/`:

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
| `crm/notes.csv` | note someone wrote by hand | on the company, or on a deal when `opportunity_id` is set; dated and authored |
| `crm/meetings.csv` | call on the calendar | `booked_on` is the day it was booked, `starts_at` when it happens (UTC) |
| `crm/followups.csv` | follow-up an owner scheduled on an account | `due_on` is when it is due; `status` open or done, with `completed_on`; an open follow-up is what makes an at-risk account *acknowledged* |
| `crm/emails.csv` | email sales logged with a contact | `direction` outbound or inbound, `sent_at` UTC; on a deal when `opportunity_id` is set |
| `crm/calls.csv` | call sales logged with a contact | `outcome` connected, voicemail or no_answer; `minutes`; the owner's notes in `body` |
| `arcs.csv` | story arc | what each arc should surface as, and what it must not |
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
- **Dates are ISO `YYYY-MM-DD`.** Treat **2026-06-27**, `as_of` in `book.json`, as "today".
  The workbooks' CRM records were written in early May 2026; the logged emails and calls run
  from March to 2026-06-25, and open follow-ups fall due between early June and mid-July. A
  demo that wants the story to stay current should turn dates into an age relative to that day.
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

## The arcs

The workbooks were written as a believable company, not as a demo, and joined they do not
tell every story the account-health demo needs: nobody withholds payment over a bug, nothing
churns quietly, and no account is noisy but fine. `apply_arcs.py` makes each one true in the
book, where every loader carries it, rather than in one system afterwards, where a reseed
would lose it.

| Arc | Account | Should surface as |
|---|---|---|
| Silent escalation | Northwind Traders | at risk (urgent case, pipeline into it); sales unaware |
| Quiet churner | Chum Bucket | at risk on three failed payments, with a renewal forecast and no case |
| Withholding | Contoso | an open bug saying "we will not pay the June invoice until the export is fixed" |
| Acknowledged trouble | Initech | at risk, and NOT a blind spot: the owner's notes name both problems |
| Failed payments | Acme | at risk on a one-off invoice two cards have bounced |
| Good payer on the 5th | Wayfarer Travel | nothing: due on the 1st, paid on the 5th, one expired card fixed next day |
| Stale deal | Globex | an open deal untouched since April (already in the data) |
| Noisy but healthy | Brightline Analytics | nothing, despite nine cases — all resolved within two days |
| Shared incident | Northwind, Contoso, Initech | one export defect across three unrelated accounts |
| Controls | Cyberlife, Dharma, Ferrari Tech, Wernham Hogg | nothing |
| Writes sandbox | the account named in `arcs.csv` | the only account a harness may write to; nothing in its data says so |
| Gone quiet | 6 contacts per salesperson | no email, call or meeting in the 30 days before as-of |
| Not emailed | the same 6, plus one control per salesperson | no email in the 30 days before as-of |
| Stalled deals | 302, 305, 311, 326, 335, 339 | open, with no email or call on the deal in the 45 days before as-of |
| Slipping deals | 308, 322, 328, 346 | open, close date before as-of |
| Open follow-ups | each of the four owners | 5 open, 2 of them past due, none on an arc account |

The last five are counted by `apply_engagements.py` from `additions/`, which asserts each one
exactly:

- **Gone quiet** counts never-contacted people too, and finds nobody extra: every other contact
  had an outbound email between 2026-06-02 and 2026-06-26.
- **Not emailed** adds one control per salesperson: newest email 45+ days old, but a connected
  call within 25 days. A reader that counts only email finds the control; one that counts any
  contact does not.
- **Stalled and slipping** do not overlap: every stalled deal's close date lies after as-of,
  and every slipping deal had an outbound email or call on it within 45 days.
- HubSpot's "last contacted" leaves out inbound email, so each set is asserted both with and
  without inbound email, and comes out the same.

An *engagement* is an email, a call or a meeting, which is what a CRM counts as contact; a
note is not. A contact's `last_activity_on` is their newest engagement, and a deal's
`modified_on` is at least its newest email or call. No engagement, close date or due date sits
within four days of its cut-off, so shifting the dates or a time zone cannot change a count. A
harness that asks days after seeding must count from its own today.

**Group contagion is not seeded.** The book has no parent/subsidiary links, so there is no
group for trouble to spread through; inventing one belongs in the book's schema.

It also writes the **manual history** an agent is later asked to learn from: an AR clerk's
note the day after every failed card (`crm/notes.csv`, 35 of them), and the calls a
salesperson booked each Monday for every account overdue that day (`crm/meetings.csv`: 12
calls, on the 5 of 12 Mondays when the list was not empty). The
failed cards are added before an invoice's successful payment, so every one still ends paid.

Every arc's invariant is asserted before anything is written, and `arcs.csv` records what
each should and must not surface as, for a harness to check against.

## Domains

Every company in `book/` sits on `<name>.example.com`, its emails and websites with it:
`stark.com` becomes `stark.example.com`. `to_book.py` rewrites the whole book last. Several
workbook domains belong to real businesses, and a fictional customer joined to live enrichment
or news by domain would attract a real company's headlines; `example.com` is reserved, so
nothing here can reach anyone. It is not the reserved `.example` top level because CRMs
validate contact emails, and HubSpot rejects it. `csv/` keeps the domains as authored.

## Known quirks

Left as authored, recorded here so nobody rediscovers them:

- The workbook README tabs state 47 charges and 40 issues; the tabs hold 48 and 39.
- Charge `ch_globex_pilot_001` belongs to Acme, despite its name.
- Soylent Green Foods' domain is spelled `solyent.com`, consistently, in both contact and company.
- `csv/` keeps the workbooks' domains, several of which belong to real businesses
  (`stark.com`, `hyperion.com`, `oceanic.com`). Load `book/`, which does not.
- Company names are borrowed from film and television. Weigh that before making this public.

## Updating

Edit in Google Sheets, never here. Then, per sheet: File → Download → Microsoft Excel, put
the file in `source/` under the same name, and run:

    python3 convert.py && python3 to_book.py      # to_book.py lays the arcs over the book last

The first rewrites `csv/` and exits non-zero if the datasets stopped agreeing — a billing customer
pointing at a missing company, an issue from an unknown contact, a deals total that no
longer matches its rows. Review the CSV diff, commit both, tag.

Needs Python 3 and `openpyxl`.
