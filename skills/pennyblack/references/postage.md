# Which postage service, and what each one actually proves

Read this before advising anyone which service to buy. The intuitive answer is
often wrong, and the difference between the cheapest and dearest option is more
than a factor of ten.

All prices are Intelliprint's published rate card effective 5 January 2026, for
a single-sided A4 letter in a C5 envelope, excluding VAT. They include printing,
the envelope and the postage. The `draft` step always returns the real figure -
never quote this table as final.

| `--service` | Service | Price | Signature | Tracked | Compensation |
|---|---|---|---|---|---|
| `second` | Royal Mail 2nd Class | £0.84 | no | no | £20 |
| `first` | Royal Mail 1st Class | £1.94 | no | no | £20 |
| `signed-second` | Signed For 2nd Class | £3.51 | yes | no | £20 |
| `signed` | Signed For 1st Class | £4.34 | yes | no | £20 |
| `tracked-48` | Tracked 48 | see note | optional | yes | £75 |
| `tracked-24` | Tracked 24 | see note | optional | yes | £75 |
| `special` | Special Delivery by 1pm | £11.35 | yes, viewable | yes | £750 |
| `special-9am` | Special Delivery by 9am | £48.97 | yes, viewable | yes | £50+ |

## The misconception worth correcting

People buy Signed For because they want to prove a letter was served. **It does
not do that**, and it is worth saying so before they pay four times the price of
first class for it.

Under **CPR 6.26**, a document sent by first class post is deemed served on the
second business day after posting. In **Diriye v Bojaj (2020) EWCA Civ 1400**,
the Court of Appeal held that a Signed For 1st Class delivery is still deemed
served on that same second day, *regardless of when it was actually signed for*.
The Court's reasoning was that Signed For is simply a species of first class
post, and that the whole point of the deemed-service regime is to make actual
service irrelevant.

And what **CPR Part 6** requires a certificate of service to state is the **date
of posting** - not proof of delivery.

Two further limits, from Royal Mail's own documentation:

- The signature captured is whoever accepted the item. Royal Mail says it "might
  not match the name on the address label, and could be a neighbour or other
  person at the delivery address".
- For Signed For, Royal Mail does not give you a copy of the signature at all.
  Only Special Delivery provides a signature scan you can view.

So:

- **If the goal is a court-proof date** - first class is sufficient, and cheap.
  Keep the proof of posting.
- **If the goal is a record that it arrived, plus a deterrent** - Signed For is
  reasonable. It creates a delivery confirmation and it makes the recipient
  engage with the item.
- **If the goal is evidence that will be challenged** - Special Delivery. It is
  the only service producing a signature you can actually look at, with £750
  cover.

## Tracked 24 and Tracked 48: a trap

Royal Mail's Tracked 24 and Tracked 48 **have no Letter-format rate**. Their
price tables start at Large Letter. A `tracked-24` or `tracked-48` request on an
ordinary letter is therefore being priced as a larger format, which is why the
rate card does not show a comparable per-letter figure.

For a single sheet in a C5 envelope, `signed` gets you a signature *and* a
tracking number for less than tracked-as-a-large-letter usually costs. Prefer
Signed For unless the recipient specifically needs the in-transit scans.

## Compensation is £20, not £50

Signed For compensation is capped at **£20** or the value of the item, whichever
is lower. Many third-party guides still say £50 - that figure was withdrawn in
the 2024 update. If the contents are worth more than £20, the service does not
cover them, and Special Delivery (£750) is the honest answer.

## Recorded Delivery does not exist any more

If someone asks for "recorded delivery", they mean `signed`. The product was
renamed **Recorded Signed For** in May 2003 and then **Royal Mail Signed For**
on 2 April 2013. There is no separate Recorded Delivery service to buy.

## Which tracking numbers you get

The API issues a Royal Mail tracking number for these services only:

`signed`, `signed-second`, `tracked-24`, `tracked-48`, `special`, `special-9am`

Plain `first` and `second` produce no tracking number, because there is nothing
to track. The number appears once the item is dispatched, not at the moment you
confirm the job - so `status` a day later, not immediately.

## Sources

- Royal Mail service pages for Signed For 1st and 2nd Class, Special Delivery by
  1pm and 9am, Tracked 24 and 48, 1st and 2nd Class
- Civil Procedure Rules Part 6 - https://www.justice.gov.uk/courts/procedure-rules/civil/rules/part06
- Diriye v Bojaj (2020) EWCA Civ 1400, via Littleton Chambers
- Intelliprint rate card - https://www.intelliprint.net/pricing
- Intelliprint OpenAPI spec - https://www.intelliprint.net/openapi.json
