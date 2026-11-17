### Added

- `plan_query`: each plan step has an optional `call` field, the arguments of a first call to
  its tool as JSON, with `<...>` where only the question can supply a value (`{"vector_ids":[<ids>],"latest_n":1}`).
  Every tool gets one from its required arguments in the tool catalogue, and 21 of the most used
  tools (WDS, CMHC, the census profile, the open-data portals) have a written recipe. A model can pass it to
  `call_tool` without a `search_tools` call first.

### Changed

- `plan_query`: a plan leaves out steps the question does not need: Borealis, the 2001-2016 census
  archive and the boundary maps unless the question asks for them; Alberta's dashboard unless the
  question is about Alberta; occupation, wage, methods and Toronto building-score steps unless the
  question uses their words; an Edmonton rent question no longer lists Edmonton Police, Transit
  and EPCOR; a permit, licence, inspection or planning question that names a city lists only that
  city's (or its province's) records. The plan's output is not larger on average than before.
