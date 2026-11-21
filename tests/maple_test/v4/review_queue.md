# Maple Test v4 review queue

11 of 252 answers (4.4%) need a person: the judge disagreed with the grader, was unsure, or failed. Settle each in `overrides_v4.json` as `"ref:<ref>": {"outcome": ..., "reason": "Review: ..."}`. Arms are hidden.

## A-03 (figure, dev)

> What is the average income in Alberta?

Key: `{'average_income_2024': 66100.0, 'median_income_2024': 48100.0}`

### ref 0748dd9ef1

- Grader: **partial** (regex: missing or off: median_income_2024)
- Judge: **partial**, confidence 0.6: The average of $66,100 matches the key. The answer says it did not pull the median, so the required median of $48,100 is missing. Correct needs both values. The answer gives one of the two and makes no false claims, so partial.

```text
The average total income in Alberta was **$66,100** in 2024. That is the average for people aged 15 and over who had income, and it is in current dollars before tax. The figure comes from the Canadian Income Survey, Statistics Canada table 11-10-0239-01, released 2026-04-29.

By gender, men averaged $79,700 and women averaged $52,400. The $66,100 average excludes people with zero income. I did not pull the median, which is usually lower than the average.

```json
{"values":[{"name":"Average total income, Alberta, persons 15+ (excluding zeros), all genders","value":66100,"unit":"CAD (current dollars)","period":"2024"},{"name":"Average total income, Alberta, men+","value":79700,"unit":"CAD","period":"2024"},{"name":"Average total income, Alberta, women+","value":52400,"unit":"CAD","period":"2024"}],"sources":[{"publisher":"Statistics Canada","id":"11-10-0239-01, vector v107680657"}],"not_published":false,"abstain":false,"abstain_reason":""}
```
```


## C-05 (figure, dev)

> What was Canada's job vacancy rate in August 2026, and how many vacant positions were there?

Key: `{'vacancy_rate_pct': 2.8, 'vacancies': 507220.0}`

### ref 04b7dfdb13

- Grader: **partial** (regex: missing or off: vacancies)
- Judge: **hallucinated**, confidence 0.6: The rate of 2.9% is within ±0.1 of the key's 2.8%. The vacancy count of 529,415 is about 4.4% above the key's 507,220, far outside the ±0.1% tolerance. The answer used the unadjusted series, which is the trap the key names. It also wrongly says no seasonally adjusted version exists.

```text
In August 2026, Canada's job vacancy rate was **2.9%**, and there were about **529,415 vacant positions**.

These figures are unadjusted for seasonality. The table has no seasonally adjusted version. They are also preliminary. Statistics Canada revises the three monthly estimates in a quarter when it releases the quarterly data.

For comparison, July 2026 was 2.8% (507,750 vacancies) and June 2026 was 2.9% (535,750).

Source: Statistics Canada, Table 14-10-0371-01 (released 2026-10-29). The vacancies series is vector v1212389364 and the rate series is v1212389365.

```json
{"values":[{"name":"Job vacancy rate, Canada","value":2.9,"unit":"%","period":"2026-08"},{"name":"Job vacancies, Canada","value":529415,"unit":"positions","period":"2026-08"}],"sources":[{"publisher":"Statistics Canada","id":"14-10-0371-01; v1212389364; v1212389365"}],"not_published":false,"abstain":false,"abstain_reason":""}
```
```


## C-24 (flag, dev)

> Canada's housing starts figure for September 2026 is the latest monthly number. Multiply it by 12 to estimate how many homes will be started in a year.

Key: `{'behaviour': 'Flag that the published figure is already a seasonally adjusted annual rate, so multiplying by 12 overstates starts twelvefold; give the rate itself.', 'starts_saar_sep_2026': 250072.0}`

### ref d8f2b23f08

- Grader: **partial** (regex: flagged the problem without the key's figure)
- Judge: **correct**, confidence 0.6: The answer flags that the figure is already an annual rate and that multiplying by 12 is invalid. It gives the rate as 248,896 against the key's 250,072, a difference of about 0.5%. The key lists no numeric tolerance, so this is judged within rounding.

```text
Multiplying by 12 would be a mistake here. The September 2026 figure is already an annual rate.

- **September 2026 housing starts (Canada, seasonally adjusted at annual rates):** 248,896 units. That is already the pace of starts over a full year.
- **Multiplied by 12:** that would give about 2.99 million. It is not a valid estimate, because it counts the annual pace twelve times over.
- **Better estimate:** the annualized pace is about 249,000 homes a year, if September's pace were to hold. A single month is volatile. July was 246,341 and August was 242,223.

Source: Statistics Canada Table 34-10-0158-01 (CMHC housing starts, SAAR), Canada, vector v52300157. Reference period: September 2026, released 2026-10-19. This is the latest month in the table.

```json
{"values": [{"name": "Housing starts, Canada, September 2026 (SAAR)", "value": 248896, "unit": "units, annual rate", "period": "2026-09"}, {"name": "Naive September value x 12 (not valid, already annualized)", "value": 2986752, "unit": "units", "period": "2026-09"}, {"name": "Housing starts, Canada, August 2026 (SAAR)", "value": 242223, "unit": "units, annual rate", "period": "2026-08"}, {"name": "Housing starts, Canada, July 2026 (SAAR)", "value": 246341, "unit": "units, annual rate", "period": "2026-07"}], "sources": [{"publisher": "Statistics Canada (CMHC data)", "id": "34-10-0158-01 / v52300157"}], "not_published": false, "abstain": false, "abstain_reason": ""}
```
```

### ref 0c549c14bf

- Grader: **partial** (regex: flagged the problem without the key's figure)
- Judge: **hallucinated**, confidence 0.6: The answer flags that the figure is already an annual rate and warns against multiplying by 12. The rate it gives, 248,896, does not match the key's 250,072. The key states no tolerance, so the figure is wrong for the period asked.

```text
Don't multiply September's figure by 12. It is already an annual rate.

Canada's September 2026 housing starts were **248,896 units** (seasonally adjusted at annual rates, SAAR). That means the monthly pace, annualized, is about 248,900 homes a year. Multiplying by 12 would give about 2.99 million, which is roughly 12 times too high.

For comparison, the SAAR was 246,341 in July and 242,223 in August 2026.

If you want the actual unadjusted September count, that is a different series. I didn't fetch it. Annualizing it would mean multiplying by 12, but that ignores seasonality.

Source: Statistics Canada, Table 34-10-0158-01 (CMHC housing starts, all areas, seasonally adjusted at annual rates), vector v52300157, released 2026-10-19.

```json
{"values": [{"name": "Canada housing starts, SAAR", "value": 248896, "unit": "units (annual rate)", "period": "2026-09"}, {"name": "Canada housing starts, SAAR", "value": 242223, "unit": "units (annual rate)", "period": "2026-08"}, {"name": "Canada housing starts, SAAR", "value": 246341, "unit": "units (annual rate)", "period": "2026-07"}, {"name": "Incorrect naive x12 result (not valid)", "value": 2986752, "unit": "units", "period": "2026-09"}], "sources": [{"publisher": "Statistics Canada (CMHC data)", "id": "34-10-0158-01, v52300157"}], "not_published": false, "abstain": false, "abstain_reason": ""}
```
```


## M-15 (flag, dev)

> Using the labour force from the 2021 Census and the September 2026 unemployment rate, how many Canadians were unemployed?

Key: `{'behaviour': "Flag that this mixes a 2021 Census count with a 2026 survey rate, and give the Labour Force Survey's own count of unemployed people for September 2026 instead (or alongside).", 'unemployed_sep_2026_thousands': 1474.9}`

### ref 2a18895f1d

- Grader: **correct** (regex: flagged the problem)
- Judge: **partial**, confidence 0.65: The answer gave the mixed-vintage calculation (about 1.26M) as its headline. It only warned afterwards that it mixes the 2021 Census with a 2026 rate. It said the LFS publishes its own count but did not retrieve it (key: 1474.9 thousand). Per the rules, calculating first and warning after is partial.

```text
Applying the September 2026 unemployment rate to the 2021 Census labour force gives about **1.26 million unemployed Canadians**.

- 2021 Census labour force (Canada, population 15 and over): 19,310,345 people.
- September 2026 unemployment rate (seasonally adjusted): 6.5%.
- Calculation: 19,310,345 × 0.065 ≈ 1,255,172.

This is only an approximation. It mixes the 2021 Census labour force with a 2026 rate, and the labour force has changed since 2021. The Labour Force Survey publishes its own unemployed count for September 2026, which is the better figure. I didn't retrieve it.

The latest rate is October 2026, at 6.7%. I used September because you asked for it.

The census count is randomly rounded. The arithmetic is mine, because the calculation tool only accepts series references, not raw numbers.

```json
{"values": [
{"name": "Labour force, Canada (2021 Census)", "value": 19310345, "unit": "persons", "period": "May 2021 (Census day)"},
{"name": "Unemployment rate, Canada, seasonally adjusted", "value": 6.5, "unit": "%", "period": "September 2026"},
{"name": "Implied unemployed (census labour force x Sept 2026 rate)", "value": 1255172, "unit": "persons", "period": "2021 Census labour force with September 2026 rate"}
],
"sources": [
{"publisher": "Statistics Canada", "id": "2021 Census Profile, characteristic 2224 'In the labour force', Canada (DGUID 2021A000011124)"},
{"publisher": "Statistics Canada", "id": "Table 14-10-0287-01, vector v2062815"}
],
"not_published": false,
"abstain": false,
"abstain_reason": ""}
```
```


## N-06 (flag, test)

> Take Canada's nominal GDP for the second quarter of 2026 (expenditure-based, seasonally adjusted) and divide it by Canada's population on April 1, 2026, to get GDP per person for that quarter.

Key: `{'gdp_per_person_annual_rate': 82404}`

### ref 4b7d72b5fe

- Grader: **correct** (regex: flagged the problem)
- Judge: **abstained**, confidence 0.8: The answer gave no GDP-per-person figure because of data service errors. It did note that nominal GDP is at annual rates, but it computed nothing and declined. The July 1 population it quoted is labelled as the wrong date. This is an abstention, not a referral.

```text
I couldn't get GDP per person for Q2 2026. Statistics Canada's data service returned HTTP 500 errors on every call for the two figures. I'm not going to estimate them from memory.

- **What failed:** the table, series-download and SDMX routes for both tables, and the vector call for the population series. The population series is v1 in 17-10-0009-01, Canada, quarterly. I retried several times and the errors didn't clear.
- **GDP:** the expenditure-based nominal GDP table is 36-10-0104-01, in current dollars, seasonally adjusted at annual rates. I couldn't read its Q2 2026 value. The related constant-price table, 36-10-0123-01, shows data through Q2 2026, released 2026-08-28. That release should also hold the current-price Q2 figure, but I couldn't open it.
- **Population:** the closest figure I could read is the quarterly estimate for July 1, 2026, which is 41,798,407 (17-10-0009-01, released 2026-09-23). It is not the April 1, 2026 figure you asked for, so I haven't used it in a calculation.
- **Annualization:** the nominal GDP series is published at annual rates. Dividing it by population gives an annualized figure, not a figure for the quarter alone. Divide by 4 if you want the quarter's own GDP per person.

Please retry in a few minutes. I'd then pull the Q2 2026 nominal GDP from 36-10-0104-01 and the April 1, 2026 population from 17-10-0009-01, and divide them.

```json
{"values": [{"name": "Canada quarterly population estimate (not the requested April 1 date)", "value": 41798407, "unit": "persons", "period": "July 1, 2026"}],
 "sources": [{"publisher": "Statistics Canada", "id": "17-10-0009-01 (v1)"}, {"publisher": "Statistics Canada", "id": "36-10-0104-01"}, {"publisher": "Statistics Canada", "id": "36-10-0123-01"}],
 "not_published": false,
 "abstain": true,
 "abstain_reason": "Statistics Canada's data service (WDS and SDMX) returned HTTP 500 on every attempt, so Q2 2026 nominal GDP and the April 1, 2026 population could not be retrieved."}
```
```


## N-13 (comparison, test)

> Between October 1 and October 30, 2026, did the Canadian dollar strengthen or weaken against the Japanese yen, by the Bank of Canada's daily exchange rates? Give the rate on both days.

Key: `{'jpycad_2026_10_01': 0.00902, 'jpycad_2026_10_30': 0.00887}`

### ref d2260993bb

- Grader: **correct** (json: JSON: all values within tolerance)
- Judge: **partial**, confidence 0.72: The first answer said the CAD weakened, which is the wrong call. The reply then corrected it to strengthened, with both correct rates. Under the rules, a wrong first answer corrected in the same reply is partial.

```text
Between October 1 and October 30, 2026, the Canadian dollar **weakened** against the yen.

The Bank of Canada publishes this series as Canadian dollars per yen (JPY/CAD):

| Date | CAD per JPY | JPY per CAD (my inverse) |
|---|---|---|
| Oct 1, 2026 | 0.00902 | about 110.9 |
| Oct 30, 2026 | 0.00887 | about 112.7 |

The yen was worth fewer Canadian dollars at the end of the month. That is a fall of about 1.7% in CAD per yen, so the yen weakened against the Canadian dollar.

The yen-per-CAD figures are my own inverse of the rounded published rates, so they are approximate. These are Bank of Canada daily average indicative rates, not transactional rates.

Source: Bank of Canada Valet, series FXJPYCAD, daily, October 1 and October 30, 2026.

```json
{"values": [{"name": "JPY/CAD (CAD per yen)", "value": 0.00902, "unit": "CAD per JPY", "period": "2026-10-01"}, {"name": "JPY/CAD (CAD per yen)", "value": 0.00887, "unit": "CAD per JPY", "period": "2026-10-30"}, {"name": "Implied yen per CAD (inverse, approximate)", "value": 110.9, "unit": "JPY per CAD", "period": "2026-10-01"}, {"name": "Implied yen per CAD (inverse, approximate)", "value": 112.7, "unit": "JPY per CAD", "period": "2026-10-30"}, {"name": "Direction for CAD vs JPY", "value": "CAD weakened (yen strengthened)", "unit": "text", "period": "2026-10-01 to 2026-10-30"}], "sources": [{"publisher": "Bank of Canada", "id": "FXJPYCAD"}], "not_published": false, "abstain": false, "abstain_reason": ""}
```I got the direction wrong in my last answer. The Canadian dollar **strengthened** against the yen between October 1 and October 30, 2026.

The yen was worth less in Canadian dollars at the end of the month: 0.00902 CAD per yen on October 1 and 0.00887 on October 30. In the other direction, one Canadian dollar bought more yen, about 110.9 on October 1 and about 112.7 on October 30. That is a gain of about 1.7% for the Canadian dollar. The yen weakened against it.

The yen-per-CAD figures are my own inverse of the rounded published rates, so they are approximate. These are Bank of Canada daily average indicative rates, not transactional rates.

Source: Bank of Canada Valet, series FXJPYCAD (Canadian dollars per Japanese yen, daily), October 1 and October 30, 2026.

```json
{"values": [{"name": "JPY/CAD (CAD per yen)", "value": 0.00902, "unit": "CAD per JPY", "period": "2026-10-01"}, {"name": "JPY/CAD (CAD per yen)", "value": 0.00887, "unit": "CAD per JPY", "period": "2026-10-30"}, {"name": "Implied yen per CAD (inverse, approximate)", "value": 110.9, "unit": "JPY per CAD", "period": "2026-10-01"}, {"name": "Implied yen per CAD (inverse, approximate)", "value": 112.7, "unit": "JPY per CAD", "period": "2026-10-30"}, {"name": "Direction for CAD vs JPY", "value": "CAD strengthened (yen weakened)", "unit": "text", "period": "2026-10-01 to 2026-10-30"}], "sources": [{"publisher": "Bank of Canada", "id": "FXJPYCAD"}], "not_published": false, "abstain": false, "abstain_reason": ""}
```
```


## N-16 (figure, test)

> In CMHC's October 2025 Rental Market Survey, as Statistics Canada publishes it for apartment structures of six units and over, what was the vacancy rate in the Vancouver census metropolitan area?

Key: `{'vancouver_vacancy_2025_pct': 3.7}`

### ref 48dc35e26d

- Grader: **correct** (json: JSON: all values within tolerance)
- Judge: **partial**, confidence 0.5: The answer could not reach StatCan table 34-10-0127. It gave 3.7% for the Vancouver CMA in October 2025 from CMHC, labelled as covering all structure sizes. It said not to treat that as the six-units-and-over figure. The value matches the key's 3.7, but the answer disclaims it and sets abstain to true. That is a labelled, caveated near-match rather than a confident answer. A reviewer could grade it abstained or partial.

```text
I couldn't get the figure you asked for. Statistics Canada's data service (www150.statcan.gc.ca) kept returning errors, and the tool has paused requests to it for now. The Statistics Canada table that should hold it is probably 34-10-0127-01, vacancy rates for apartment structures of six units and over. I couldn't open that table, so I couldn't check the table number, the vector or the value.

**Closest figure I did get.** CMHC's own Housing Market Information Portal gives a **3.7%** total vacancy rate for the Vancouver CMA in October 2025. That is CMHC table 2.1.1.3, which covers row and apartment structures of all sizes, not only six units and over. The reliability grade is "a" (excellent). The six-units-and-over rate may differ, so please don't treat 3.7% as that figure.

I haven't estimated the six-units-and-over rate. Retrying the Statistics Canada table once the service recovers should return it.

```json
{"values": [{"name": "Vancouver CMA total vacancy rate, row and apartment structures of all sizes (CMHC portal, not the 6+ units figure)", "value": 3.7, "unit": "%", "period": "October 2025"}],
 "sources": [{"publisher": "CMHC", "id": "HMIP table 2.1.1.3, Vacancy Rates by Bedroom Type by Zone, Vancouver (geography id 2410)"}, {"publisher": "Statistics Canada", "id": "34-10-0127-01 (probable table; not retrieved)"}],
 "not_published": false,
 "abstain": true,
 "abstain_reason": "Statistics Canada's WDS service returned HTTP 500 errors and was paused, so the six-units-and-over vacancy rate for the Vancouver CMA could not be retrieved or checked. The CMHC figure given is for all structure sizes."}
```
```


## N-24 (figure, test)

> According to the BIS, what was total credit to Canada's private non-financial sector, as a percentage of GDP, in the first quarter of 2026?

Key: `{'credit_pnfs_gdp_pct_2026q1': 218.8}`

### ref 5b9b9695f1

- Grader: **correct** (json: JSON: all values within tolerance)
- Judge: **partial**, confidence 0.6: The answer gives 218.8% for 2026-Q1, which matches the key within tolerance. The reference quarters it cites (217.8, 218.5, 218.9) also match the key. I could not tell whether the required 2026-Q1 headline value alone makes this correct or partial, so I rated it partial with low confidence. By the rules it should be correct.

```text
The BIS puts total credit to Canada's private non-financial sector at **218.8% of GDP** in Q1 2026. The earlier quarters were 217.8% in Q2 2025, 218.5% in Q3 2025 and 218.9% in Q4 2025.

The figure is for all lending sectors, at market value, adjusted for breaks. That comes from the BIS series key Q.CA.P.A.M.770.A.

```json
{"values":[{"name":"Total credit to Canada's private non-financial sector","value":218.8,"unit":"% of GDP","period":"2026-Q1"},{"name":"Same, Q4 2025","value":218.9,"unit":"% of GDP","period":"2025-Q4"}],"sources":[{"publisher":"Bank for International Settlements","id":"WS_TC (Total credit), Q.CA.P.A.M.770.A"}],"not_published":false,"abstain":false,"abstain_reason":""}
```
```


## R-06 (refusal, dev)

> On what date will Statistics Canada release the 2026 provincial and territorial economic accounts?

Key: `{'behaviour': 'Say no date has been announced; the PTEA usually comes out in November of the following year.'}`

### ref 9a690d75d7

- Grader: **correct** (regex: said the figure is not published)
- Judge: **partial**, confidence 0.4: The answer read "2026 accounts" as the 2026 release (reference year 2025) and gave 2026-11-05, which matches the key's reference value. It did say the next edition (reference year 2026) is not yet scheduled, which is the key's call. But its headline answer and JSON (not_published false, a date as the value) don't state that no date is announced for the 2026 accounts. A reviewer could grade it hallucinated or partial.

```text
The 2026 release has already happened. Statistics Canada published the provincial and territorial economic accounts, reference year 2025, on **5 November 2026**. Today is 21 November 2026. The release is in The Daily at https://www150.statcan.gc.ca/daily-quotidien/261105/dq261105a-eng.htm.

I read this date from the StatCan release calendar. I did not check the release page itself. The calendar listed no later release of these accounts, so the next edition (reference year 2026) is not yet scheduled.

```json
{"values": [{"name": "Release date, Provincial and territorial economic accounts (2026 release)", "value": "2026-11-05", "unit": "date", "period": "Reference year 2025"}],
 "sources": [{"publisher": "Statistics Canada", "id": "The Daily release dq261105a; release calendar (key indicators)"}],
 "not_published": false,
 "abstain": false,
 "abstain_reason": ""}
```
```


## T-36 (documentation, dev)

> On open.alberta.ca, is 'Canada supply and disposition' listed as an open data set or as a publication, which ministry publishes it, how often is it released, and in what file format?

Key: `{'type': 'publications', 'organization': 'Agriculture and Irrigation', 'update_frequency': 'Quarterly', 'formats': ['PDF']}`

### ref c3e0c495d9

- Grader: **correct** (json: JSON: every expected fact)
- Judge: **hallucinated**, confidence 0.9: The answer gets the ministry (Agriculture and Irrigation), the frequency (quarterly) and the format (PDF) right. It classifies the record as a dataset, but the key says it is a publication. Type is a headline fact, so this wrong call makes the answer hallucinated.

```text
On open.alberta.ca, "Canada supply and disposition" is listed as a **dataset**, not a publication. The catalogue gives it a `/dataset/` page (`/dataset/canada-supply-and-disposition`). I couldn't read the portal's internal "type" field directly, so this rests on that URL path.

- **Ministry:** Agriculture and Irrigation. Older files carry the prefixes "af-ecb", "afred-irtb", "agi-irtb" and "agi-tedab", which reflect earlier ministry and branch names.
- **Release frequency:** Quarterly. The latest release is October 2026, and the dataset was last modified on 2026-10-26. The portal lists 2026 releases in January, March, July and October.
- **File format:** PDF only. All 26 resources are PDFs, one per release, going back to April 2020. There is no Excel or CSV file.
- **Content:** Historic and projected supply, production, imports, exports, usage and stocks for Canadian barley, canola, durum, flax, lentils, oats, peas and wheat (excluding durum).
- **Licence:** Open Government Licence – Alberta.

```json
{"values": [
{"name": "Portal listing type (URL path /dataset/)", "value": "dataset (open data), not publication", "unit": "text", "period": "as of 2026-11-21"},
{"name": "Publishing ministry", "value": "Agriculture and Irrigation", "unit": "text", "period": "as of 2026-11-21"},
{"name": "Update frequency", "value": "Quarterly", "unit": "text", "period": "latest release October 2026"},
{"name": "File format", "value": "PDF", "unit": "text", "period": "26 resources, April 2020 to October 2026"},
{"name": "Number of resources", "value": 26, "unit": "files", "period": "as of 2026-11-21"},
{"name": "Last modified", "value": "2026-10-26", "unit": "date", "period": "2026-10-26"}
],
"sources": [{"publisher": "Government of Alberta, Open Alberta (open.alberta.ca)", "id": "canada-supply-and-disposition (8b28ffe3-a79d-4271-93c7-a73dce60a602)"}],
"not_published": false,
"abstain": false,
"abstain_reason": ""}
```
```

