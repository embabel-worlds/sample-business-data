GitHub Issues Sample Data — v1 — 2026-06-27

Sample GitHub Issues data for the engineering ticketing system, linked to HubSpot contacts and companies.

Sheets included:
  • Issues  40 issues — bugs, feature requests, questions, internal items. Mix of open / closed / in-progress.
  • Labels Reference  All labels used in Issues sheet, organized by type / priority / area / context.
  • Team Reference  Engineering team members and CS reps who file/are assigned issues.


Cross-system linking:
  • Reporter Contact (HubSpot) → links to a contact in HubSpot Contacts sheet
  • Reporter Company (HubSpot) → links to a company in HubSpot Companies sheet
  • Issues filed by external customers (Sarah Johnson, Priya Patel, David Chen, etc.) directly via support portal
  • Issues filed internally on behalf of customers carry the label "filed-on-behalf" and a CS rep as Author
  • Issues with no customer (security, internal) have empty Reporter fields


Conceptual structure (system-agnostic):
  • Issue # = unique ticket identifier
  • State = open / closed (in-progress represented by Assignees + recent Updated At)
  • Author = who reported it (login handle if external, internal handle if filed on behalf)
  • Assignees = engineers actively working on it
  • Labels = type + priority + area + context (multi-dimensional categorization)
  • Milestone = target release version
  • Comments = thread depth signal
  • Body = full ticket description with context, repro steps, resolution

Distribution:
  • Open: ~21 issues / Closed: ~19 issues
  • By type: bugs (~13), feature requests (~14), questions (~3), documentation (~3), security (~2), enhancement (~1)
  • By priority: p0 (1), p1 (8), p2 (16), p3 (10), p4 (2), none (3)
  • Customer reporters: Sarah Johnson (Acme), Priya Patel (Stark), David Chen (Globex), Anna Müller (Hooli), Yuki Tanaka (Nakamoto), Olivia Brown (Oscorp), Marcus Williams (Wayne), and others
  • Internal reporters: jenna-cs, mike-cs (CS filing on behalf), eng-tomek, eng-riya (internal security/infra)

Notes:
  • All data is fictional. GitHub handles, repo names, CVE numbers are placeholders.
  • Schema follows GitHub Issues conventions but the conceptual model maps to Zendesk, Jira, Linear, or any ticketing system.
  • Repository field set to "embabel/platform" throughout — change as needed for your scenario.
**Stripe — custom fields (3):**

- Customers → `HubSpot Company ID`
- Subscriptions → `Notes`
- Disputes → `Description`

**GitHub Issues — custom fields (2):**

- Issues → `Reporter Contact (HubSpot)`
- Issues → `Reporter Company (HubSpot)`
