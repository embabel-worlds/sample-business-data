Stripe Sample Data — v1 — 2026-06-27

Sample Stripe data linked to HubSpot Sample Data. All paying customers + churned/delinquent edge cases.

Sheets included:
  • Customers  17 records — 13 active, 2 churned, 2 past-due/delinquent. Links to HubSpot Company ID.
  • Subscriptions  21 records — annual + monthly; active, canceled, past_due. Multi-sub customers shown (base + add-on).
  • Invoices  49 records — paid, open, uncollectible, void. Multiple years per customer for tenure realism.
  • Charges  47 records — succeeded, failed (with failure codes), refunded, disputed. Card / ACH / SEPA / BACS / wire.
  • Refunds  5 records — full and partial; reasons: requested_by_customer, duplicate.
  • Disputes  3 records — won, lost, warning_needs_response. Realistic chargeback patterns.

Cross-system linking:
  • Customers.HubSpot Company ID → HubSpot Companies.Record ID
  • Customer Name fields are kept consistent across both files for easy joins
  • Customers from HubSpot Customer-stage companies + select Closed-Won deals are paying customers
  • Churned customers (Vandelay, Hudsucker) and delinquent customers (Sirius, Bluth) added as edge cases

ID format conventions (Stripe-style):
  • cus_xxx  Customer
  • sub_xxx  Subscription
  • in_xxx  Invoice
  • ch_xxx  Charge
  • pi_xxx  PaymentIntent
  • re_xxx  Refund
  • du_xxx  Dispute
  • price_xxx  Price (subscription plan)

Edge cases included:
  • Failed card charges with retry sequence (Bluth Company, 3 attempts April 2026)
  • Disputed charge won in merchant favor (Acme pilot fee)
  • Disputed charge lost on technicality (Sirius Cybernetics)
  • Open dispute awaiting response (Bluth Company)
  • Customer with prorated refund after mid-term cancellation (Vandelay, Hudsucker)
  • Multi-currency: USD, EUR (SEPA), GBP (BACS)
  • Non-card payment methods: ACH, SEPA Direct Debit, BACS, wire transfer
  • Multi-subscription customers (Oscorp, Tyrell, Glimmerford, Spacely with base + add-ons)
  • Uncollectible invoice written off (Vandelay prorated cancellation fee)
  • Open/unpaid invoices currently in dunning (Bluth April invoice)

How these columns map to the real Stripe API:
  • HubSpot Company ID (Customers)  customer.metadata.hubspot_company_id  — standard pattern for CRM linkage
  • Notes (Subscriptions)  subscription.metadata.notes  — Subscriptions have no top-level notes field
  • Description (Disputes)  dispute.metadata.description or evidence text  — Disputes have no top-level description (unlike Customers/Charges/Invoices/Refunds which do)
  • Country (Customers)  customer.address.country  — flattened from address sub-object
  • Default Payment Method  customer.invoice_settings.default_payment_method  — nested in API
  • Card Brand / Card Last 4 (Charges)  charge.payment_method_details.card.brand / .last4  — nested in API
  • Amount per Period (Subscriptions)  derived from subscription.items[].price.unit_amount × items[].quantity
  • Account Balance (Customers)  customer.balance  — Stripe stores this in cents; this sheet displays dollars

Notes:
  • Amounts shown in major currency units (dollars/euros/pounds), not cents. Stripe API uses cents.
  • All data is fictional. IDs are formatted to look like Stripe but are not real.
  • Field names match Stripe's API object names where possible; see the mapping table above for flattened/nested fields.
**Stripe — custom fields (3):**

- Customers → `HubSpot Company ID`
- Subscriptions → `Notes`
- Disputes → `Description`

**GitHub Issues — custom fields (2):**

- Issues → `Reporter Contact (HubSpot)`
- Issues → `Reporter Company (HubSpot)`
