# Which postage service, and what each one actually proves

Read this before advising anyone which service to buy. The intuitive answer is
often wrong, and the difference between the cheapest and dearest option is more
than a factor of ten.

**This is postage fact, not legal advice.** It says what each Royal Mail service
does, and what pennyblack can and cannot show afterwards. Whether a letter has
been validly served or given is a legal question. If that matters to the user,
tell them to ask a solicitor. Do not answer it for them.

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

## A document that names the method

Before recommending a service, ask the user one question: does a lease, a
contract, a court order or a statute say how this letter must be sent? Notices
often do. Break notices, rent review notices, notices to quit and contract
termination notices commonly say "registered post", "recorded delivery" or
"first class post".

If one does, **that clause decides, not this file.**

- Ask the user to read the clause, or the statute it relies on, and give you
  the exact words. Do not paraphrase it for them.
- Use the method it names. Never tell the user that another method will do,
  that Signed For is "the same thing", or that first class is enough. That is a
  legal judgement, and a wrong one can cost them a valid notice.
- Where it names **registered post or recorded delivery**, use `special`
  (Special Delivery). It is the safe choice from what pennyblack offers. If the
  user wants something cheaper, that is for their solicitor to approve, not the
  agent.
- Where it names a method pennyblack cannot provide, such as delivery by hand
  or to an email address, tell the user that and stop.

Other rules apply when a document names the method, and the CPR point below
does not carry across to them. Two examples:

- The **Recorded Delivery Service Act 1962 s.1** makes an Act that requires
  registered post accept recorded delivery as well.
- Under the **Law of Property Act 1925 s.196(4)**, a notice sent by registered
  post or recorded delivery is served under that subsection only if the letter
  is **not returned undelivered**. Section 196(5) extends this to notices under
  leases and other instruments affecting property, unless they say otherwise.
  See "A returned letter" below.

## Court documents served under CPR 6.26

This section is only about documents in court proceedings, served by post under
the Civil Procedure Rules in England and Wales. It does not apply to a notice
under a lease, a contract or a statute. For those, see the section above.

People serving a court document often buy Signed For because they think it
proves service. Under the CPR it does not add anything, and for a court document
it is worth telling them before they pay four times the price of first class.

Under **CPR 6.26**, a document sent by first class post is deemed served on the
second business day after posting. In **Diriye v Bojaj (2020) EWCA Civ 1400**,
the Court of Appeal held that a Signed For 1st Class delivery is still deemed
served on that same second day, *regardless of when it was actually signed for*.
The Court's reasoning was that Signed For is simply a species of first class
post, and that the whole point of the deemed-service regime is to make actual
service irrelevant.

And what **CPR Part 6** requires a certificate of service to state is the **date
of posting** - not proof of delivery. See "Proof of posting" below for what
pennyblack can and cannot show about that date.

So for a court document served by post under the CPR, first class is the
method the rule names, and it is cheap. Signed For does not change the deemed
date.

## What each service gives you

Two limits on Signed For, from Royal Mail's own documentation:

- The signature captured is whoever accepted the item. Royal Mail says it "might
  not match the name on the address label, and could be a neighbour or other
  person at the delivery address".
- For Signed For, Royal Mail does not give you a copy of the signature at all.
  Only Special Delivery provides a signature scan you can view.

So, where no clause or rule names the method:

- **A record that it arrived, plus a deterrent** - Signed For is reasonable. It
  creates a delivery confirmation and it makes the recipient engage with the
  item.
- **Evidence that will be challenged** - Special Delivery. It is the only
  service producing a signature you can actually look at, with £750 cover.

## Proof of posting, and the posting date

**pennyblack gives no certificate of posting**, for 1st or 2nd class or any
other service. Royal Mail issues a free certificate of posting at a Post Office
counter, but a pennyblack letter is handed to Royal Mail by the print house, not
at a counter, so none is issued. Plain `first` and `second` also have no
tracking number, so there is no Royal Mail record of that item at all. If the
user needs a certificate of posting, they should print the letter and post it
themselves at a Post Office.

The date a letter was posted is the provider's `shipped_date`: the day the print
house handed it to Royal Mail. `pennyblack status <id>` shows it. It is not the
day `send` was run. It can only be the same day if the job was confirmed before
3pm.

The record's `confirmed_at` is when `send` ran. Never give it to the user as the
date of posting.

## A returned letter

If Royal Mail cannot deliver a letter, it comes back to the print house and
`pennyblack status <id>` shows the status `returned`.

For a notice served by registered post or recorded delivery under the Law of
Property Act 1925 s.196(4), a returned letter can mean the notice was not
served. Where service matters, check `pennyblack status <id>` again in the days
after sending, and tell the user at once if it shows `returned`. What to do next
is a question for their solicitor.

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

If someone asks for "recorded delivery" for an ordinary letter, they usually
mean `signed`. The product was renamed **Recorded Signed For** in May 2003 and
then **Royal Mail Signed For** on 2 April 2013. There is no separate Recorded
Delivery service to buy.

That is a product history, not a ruling on any document. If "recorded delivery"
comes from a lease, a contract or a statute, do not treat it as a plain request
for `signed`. Go back to the section on a document that names the method.

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
- Recorded Delivery Service Act 1962 s.1 - https://www.legislation.gov.uk/ukpga/Eliz2/10-11/27/section/1
- Law of Property Act 1925 s.196 - https://www.legislation.gov.uk/ukpga/Geo5/15-16/20/section/196
- Intelliprint rate card - https://www.intelliprint.net/pricing
- Intelliprint OpenAPI spec - https://www.intelliprint.net/openapi.json
