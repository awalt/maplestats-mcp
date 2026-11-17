### Fixed

- `plan_query` leaves one city's tools out of a plan for other places. A
  question about rents in Edmonton and Calgary listed RentSafeTO and Toronto's
  short-term rentals, and one about restaurant inspections in Ottawa started
  with Toronto's DineSafe. Toronto, Edmonton (`eps_`, `ets_`, `epcor_`) and
  Vancouver tools stay when the question names that city, its province, or no
  place.
