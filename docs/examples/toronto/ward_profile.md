# A ward's councillor, its RentSafeTO scores and its neighbourhoods' renter share

**Question.** Who is the councillor for Toronto's Ward 10, how do its
apartment buildings score on RentSafeTO, and what share of households rent in
the neighbourhoods it covers?

The answer draws on five City of Toronto tables on open.toronto.ca, all read
through the portal's CKAN DataStore API and all under the Open Government
Licence – Toronto:

| Figure | open.toronto.ca dataset | DataStore resource |
|---|---|---|
| Councillor | [Elected Officials' Contact Information](https://open.toronto.ca/dataset/elected-officials-contact-information/), 2022-2026 | `16d6b1b3-b474-47f4-8c09-8bf5b3aa0e68` |
| Building scores | [Apartment Building Evaluations](https://open.toronto.ca/dataset/apartment-building-evaluation/), "2023 - current" | `244f7a02-da5c-425b-b55f-fbdd133dd732` |
| Ward boundary | [City Wards](https://open.toronto.ca/dataset/city-wards/), 25-ward model | `7672dac5-b383-4d7c-90ec-291dc69d37bf` |
| Neighbourhood boundaries | [Neighbourhoods](https://open.toronto.ca/dataset/neighbourhoods/), "historical 140" | `7d3ae06b-0217-4cc9-92ed-97adafca2f7b` |
| Renter share | [Neighbourhood Profiles](https://open.toronto.ca/dataset/neighbourhood-profiles/), 2016 | `7f8eee5e-85fb-415c-aef3-c3bd4998445f` |

Contains information licensed under the Open Government Licence – Toronto.

## Through MapleStats

1. `plan_query` with the question above returns a `toronto_wards` topic whose
   first step is `toronto_get_ward_profile` (`ward=<number or name>`),
   with two caveats on combining wards and neighbourhoods.
2. `call_tool` runs it with `{"ward": "10"}`. One call returns the
   councillor, the ward's RentSafeTO summary beside the city's, its five
   lowest-scoring buildings, and each overlapping neighbourhood with its 2016
   renter share. `sources` holds a citation for each of the five tables and
   `caveats` lists what the combination cannot show.

The same answer can be built step by step with the tools that call combines:
`toronto_get_councillors` (`ward="10"`), `toronto_get_apartment_evaluations`
(`ward="10"`), `toronto_get_ward_neighbourhoods` (`ward="10"`) and
`toronto_compare_neighbourhoods` (`characteristic="Renter"`,
`divide_by_parent=True`). The full response from the run below is
`output/ward_10_profile.json`.

## Result (run on 2026-11-18)

**Councillor.** Ward 10, Spadina-Fort York: Ausma Malik (2022-2026 term, as
the City last published the table).

**RentSafeTO.** The ward has 62 evaluated buildings (10,610 units) at their
latest evaluation since 2023. Their mean score is 90.4 and the median 93,
against 90.9 and 92 for the city's 3,611 buildings. The lowest is
15 Gore Vale Ave (45, evaluated 2026-08-19), followed by 164 Grange Ave (71),
49 McCaul St (73), 25 Henry Lane Terrace (76, TCHC) and 165 Bathurst St (79).

**Neighbourhoods.** Six of the City's 140 neighbourhoods overlap the ward:

| Neighbourhood | Share of the ward | Share of the neighbourhood in the ward | Evaluated buildings in the ward | Their mean score | Renter share, 2016 |
|---|---|---|---|---|---|
| Waterfront Communities-The Island (77) | 69% | 97% | 20 | 90.9 | 59% |
| Niagara (82) | 17% | 100% | 10 | 92.9 | 50% |
| Trinity-Bellwoods (81) | 5% | 54% | 5 | 80.6 | 48% |
| Kensington-Chinatown (78) | 4% | 46% | 15 | 86.6 | 71% |
| Bay Street Corridor (76) | 3% | 28% | 1 | 90.0 | 68% |
| South Parkdale (85) | 2% | 16% | 2 | 91.5 | 87% |

Toronto's renter share in 2016 was 47%. Nine of the ward's evaluated buildings
have no coordinates in the RentSafeTO table, so they are in the ward summary
but in no neighbourhood row.

## How the pieces are joined

- The ward of a building is the City's own `WARD` field in the RentSafeTO
  table. Its neighbourhood comes from its coordinates, tested against the
  140 neighbourhood boundaries.
- The overlap of the ward and a neighbourhood is measured on the two
  published boundaries along east-west lines about 55 m apart. The sum of
  all 25 wards comes to 642 km², close to the city's land area in the 2021
  census (about 631 km²). Area shares are not population shares.
- The renter share is the "Renter" row divided by "Total - Private households
  by tenure - 25% sample data" in the 2016 profile, the row it sits under.

## What this does not show

- **A ward-level renter share.** Wards and neighbourhoods do not nest.
  Kensington-Chinatown's 71% covers the whole neighbourhood, less than half of
  which is in Ward 10. Averaging the six shares by area would assume renters
  are spread evenly across each neighbourhood. The City's Ward Profiles
  (2021 census by ward) would answer this, but they are published only as
  Excel files, which MapleStats does not download from Toronto's portal (its
  robots.txt disallows automated file downloads).
- **One year.** The tenure figures are from the 2016 census, the scores from
  2023 to 2026, and the councillor from the 2022-2026 term. Waterfront
  Communities-The Island has grown a great deal since 2016, so its share may
  have moved. The 2021 profiles use the 158-neighbourhood model and are also
  Excel-only.
- **Every renter.** RentSafeTO covers buildings with three or more storeys or
  ten or more units. Renters in houses, basements and small buildings count
  in the census share but have no score.
- **A weighted score.** A mean of building scores weights a 10-unit building
  like a 500-unit one.
- **Anything about one landlord or building beyond its score.** A low score
  is one evaluation; the table records when it was done.

## Run it

In a chat client connected to MapleStats, ask the question above. To repeat
the call from Python against a local copy of the server:

```python
import asyncio

from fastmcp import Client

from maplestats_mcp.server import mcp


async def main():
    async with Client(mcp) as session:
        result = await session.call_tool(
            "call_tool",
            {"name": "toronto_get_ward_profile", "arguments": {"ward": "10"}},
        )
        print(result.content[0].text)


asyncio.run(main())
```

The figures will move as the City adds evaluations and updates its council
table.
