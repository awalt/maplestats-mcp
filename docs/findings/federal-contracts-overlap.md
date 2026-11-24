# Federal contracts: proactive disclosure, CanadaBuys contract history and award notices

Checked 2026-11-24 for issue #253, on one fiscal year (2024-25) and two
departments (National Defence and Public Services and Procurement Canada,
PSPC). This note says what each source counts, how far they overlap and how
to use them together without counting a contract twice.

**CanadaBuys is not part of MapleStats.** Its module was removed on 2026-10-03
for its terms, and on 2026-11-24 the owner had it left out of the `ckan_` tools
too (canadabuys.canada.ca's robots.txt disallows every automated agent). This
note is a record of the comparison, made once with files downloaded by hand,
not a guide to a source this server serves. In MapleStats, federal contracts
come from proactive disclosure alone: use `disclosure_summarize` for a
department's totals.

## The three sources

| | Proactive disclosure, contracts over $10,000 | CanadaBuys contract history | CanadaBuys award notices |
|---|---|---|---|
| Publisher | Every federal department, through TBS | PSPC | PSPC (CanadaBuys) |
| In this server | `disclosure_search_contracts`, `disclosure_summarize` | Not served (see Access) | Not served (see Access) |
| Who it covers | Each department's own contracts, whoever signed them | Contracts PSPC signed (`contractingEntityName` is PSPC on all 6,967 rows of 2024-25); the buying department is `endUserEntitiesName` | Notices from PSPC (4,120 rows in 2024-25) and 247 other entities that publish on CanadaBuys (2,205 rows) |
| Threshold | Over $10,000, including amendments that take a contract over it | None observed: 1.1 % of 2024-25 contracts are under $10,000, and 98 % of supply arrangements and 68 % of standing offers carry a $0 value | None observed |
| Row | One per contract or amendment, with `contract_value` the amended total including taxes | One per contract or amendment (`amendmentNumber` 000, 001, ...) | One per contract: the latest notice for it in that year's file |
| Year of a row | `reporting_period`: the quarter it was published (a 2024-25 search returned contracts dated from 2002) | Award date: the 2024-25 file holds awards dated 2024-04-01 to 2025-03-31, and amendments published as late as 2026-10-27 are added to it | Publication date (2024-04-01 to 2025-03-31) |
| Identifier | `procurement_id`, chosen by the department: often its own purchase order (`4502863637`), sometimes the PSPC contract number in one of many spellings | `contractNumber`, the PSPC contract number (`CW2402063`, `W8482-242123/001/ML`); `referenceNumber` is the same value | `referenceNumber` (`CW...` for PSPC, `cb-...` for others) and `contractNumber` |
| Standing offers and supply arrangements | Each call-up is a row (`contracting_entity` `DSOSA`, `PWSOSA`, `SSCSOSA`), citing the offer in `standing_offer_number` | The offer or arrangement itself is a row, usually with no value; call-ups against a supply arrangement appear as "Contract against SA" | As in contract history |
| Update | Quarterly, within a month of quarter end; late entries go to past quarters | Monthly on the portal record (`P1M`); files last modified 2026-10-28 | Daily files (checked 2026-09-22) |

`contracting_entity` in proactive disclosure says who signed: `DC` the
department, `PWC` PSPC on the department's behalf, `DSOSA` and `PWSOSA`
call-ups against departmental or PSPC standing offers, `SSCC` and `SSCSOSA`
Shared Services Canada, `OGDC` another department. In 2024-25, `PWC` rows
were 5 % of the original contracts dated in the year but 86 % of their value.
Most of the money in proactive disclosure therefore went through PSPC, which
is what CanadaBuys contract history lists.

## How far they overlap

The two sources share no identifier. Of 2,507 contracts (contracts, call-ups
against supply arrangements and task-authorization contracts of $10,000 or
more) in the 2024-25 contract history file, 10.5 % have a `procurement_id` in
proactive disclosure (reporting periods 2024-25 and 2025-26, 178,019 rows)
equal to the PSPC contract number or its file number (the part before the
first `/`). Matching on the vendor (first six letters), a value within 0.5 %
(or up to 15.5 % higher, for taxes) and dates within 30 days finds 36.5 %.
Either test finds 42.2 %. The same vendor, value and date test with the award
dates moved 120 days finds 5.6 % to 10.1 %, so a few points of the 36.5 % are
chance pairs.

From the other side, 1,067 original contracts dated in 2024-25 that
departments report as signed by PSPC (`PWC`) were looked for in the contract
history file: 7.1 % by number, 22.7 % by number or by vendor, value and date,
covering 47.5 % of their value. The largest one not found is a $3.5 billion
Vancouver Shipyards contract (`procurement_id` 4500084509, 2025-03-07).

Award notices and contract history overlap only for PSPC: 61 % of the PSPC
award notices of 2024-25 have a contract number in the 2024-25 contract
history file. The rest sit in other years' files, because one file is cut by
publication date and the other by award date (the median notice is published
6 days after the award, the 75th percentile 43 days). Award notices from other
entities are not in contract history at all. For National Defence, 273 of its
364 own notices (75 %) match its proactive disclosure by contract number or by
vendor and award date.

A few examples:

- `CW2352008` (Canor Construction, $907,442.43, 2024-05-06) is in all three
  forms: contract history, the award notice, and National Defence's
  disclosure with the same number, signed by PSPC (`PWC`).
- `CW2287500` (Seaspan Marine, awarded 2024-04-05): contract history has
  $1,043,034.30; National Defence disclosed $760,691.40 under the same
  number in 2024-25 Q3.
- `CW2394075` (SIRVA Canada, $98.2 million, National Defence end user) and
  `CW2402063` (Bird Construction, $16.6 million, PSPC end user) are in
  contract history and were not found in proactive disclosure by any test.
- `W0046-25-136-0` (Calian, a National Defence amendment signed by PSPC) and
  many other `PWC` rows (`W8482-4502659386`, `4502523472`) use the
  department's own numbering, which contract history does not carry.

## Double counting

- **Do not add the sources together.** Most of the dollars in proactive
  disclosure are PSPC contracts, and contract history lists the same
  contracts again under PSPC numbers. Since no key links them, a sum of both
  counts most of that value twice, and a de-duplication by matching misses
  more than half of the pairs.
- **Do not add rows within contract history.** `totalContractValue` is the
  contract's current total and is repeated on every amendment row (all 4,260
  contracts of 2024-25). Summed over rows, the 2024-25 file gives $43.6
  billion; one row per contract (the highest `amendmentNumber`) gives $22.3
  billion. `numberOfRecords` is the number of rows the contract has; it equals
  the rows in the file for 96.7 % of contracts, and the rest have rows in
  another year's file. `contractAmount` is the original value on row 000 and
  the change on each amendment; it sums to the total for 82 % of contracts
  whose rows are all in the file.
- **Do not add rows within proactive disclosure.** Each amendment restates
  the whole amended value. `disclosure_summarize` keeps the latest row of
  each agreement.
- **Standing offers are not spending.** Contract history lists the offer or
  arrangement, usually at $0; proactive disclosure lists the call-ups. For
  National Defence, 355 call-ups citing offers awarded in 2024-25 summed $14.2
  million while those offers carry $161.7 million in contract history; for
  PSPC, 150 call-ups summed $84.1 million against $5.9 million. Neither figure
  predicts the other.
- **Do not mix years.** The same contract is in the 2024-25 contract history
  file (award date), in a later proactive disclosure year when it is amended
  (reporting period), and possibly in the 2025-26 award notice file
  (publication date).

## Using them together

- For what a department spent on contracts, use proactive disclosure alone
  (`disclosure_summarize`, which keeps the latest amendment). It covers every
  signer, PSPC included.
- Outside MapleStats, for what PSPC bought and for whom, use contract history
  alone, one row per `contractNumber`, grouped by `endUserEntitiesName` (whose
  spellings vary: "Department of National Defence (DND)" and "Department of
  National Defence").
- To follow one contract across sources, search proactive disclosure by
  vendor and date near the award date, and check the value; do not expect the
  PSPC number to be there.

## Access

The CanadaBuys files are linked from the open.canada.ca record
`4fe645a1-ffcd-40c1-9385-2c771be956a4` (Open Government Licence - Canada) but
served from canadabuys.canada.ca, whose robots.txt (read 2026-11-24) allows
only Google's and Bing's crawlers (`User-agent: *` / `Disallow: /`). This is
the host whose terms led to removing the `canadabuys` module on 2026-10-03.
The generic CKAN reader did not block that host, and on 2026-11-14 it read
the 2025-26 file (issue #253). Since 2026-11-24 it does: the hosts and the
federal portal's CanadaBuys datasets are left out of every `ckan_` tool. The fiscal-year files used here (contract history 2024-25,
18.9 MB; award notices 2024-25, 24.0 MB) were each downloaded once by hand for
this note. Proactive disclosure was read with the server's own client
(`proactive_disclosure.client.scan`).
