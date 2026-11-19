from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance


class DatasetSource(BaseModel):
    """Which open.toronto.ca table the rows come from and how to cite it."""

    dataset: str = Field(description="Dataset title on open.toronto.ca.")
    landing_page: str
    resource_id: str = Field(
        description="DataStore resource id; ckan_datastore_search with portal='toronto' reads "
        "the same table unchanged."
    )
    licence: str = Field(description="Open Government Licence - Toronto, with its link.")
    citation: str = Field(description="A citation line to quote with the figures.")


class ProfileRow(BaseModel):
    category: str | None
    topic: str | None
    characteristic: str = Field(description="Indicator label, leading spaces removed.")
    level: int = Field(
        description="Depth in the census hierarchy (0 = top line), read from the label's "
        "leading spaces: '  Renter' is level 1 under 'Total - Private households by tenure'."
    )
    data_source: str | None = Field(
        description="The census product the row comes from (2016 only), e.g. "
        "'Census Profile 98-316-X2016001'."
    )
    value: str | None = Field(description="The neighbourhood's value as published.")
    value_number: float | None = Field(description="`value` as a number, when it is one.")
    city_value: str | None = Field(description="The City of Toronto value as published.")
    city_value_number: float | None


class NeighbourhoodProfile(BaseModel):
    census_year: int
    neighbourhood: str = Field(description="Neighbourhood name as the City writes it.")
    neighbourhood_number: str | None = Field(
        description="The City's 140-model neighbourhood number (2016 table only)."
    )
    topic_filter: str | None
    characteristic_filter: str | None
    total_matched: int
    returned_count: int
    offset: int
    rows: list[ProfileRow]
    topics: list[str] = Field(description="Every topic in this census year's table, in order.")
    source: DatasetSource
    provenance: Provenance


class ApartmentEvaluation(BaseModel):
    rsn: str = Field(description="RentSafeTO registration number of the building.")
    address: str | None
    ward: str | None = Field(description="City ward number, '01' to '25'.")
    ward_name: str | None
    property_type: str | None = Field(description="PRIVATE, TCHC or SOCIAL HOUSING.")
    year_built: int | None
    year_registered: int | None
    storeys: int | None
    units: int | None
    evaluation_date: str | None = Field(description="Date the evaluation was completed.")
    score: float | None = Field(description="Current building evaluation score, 0 to 100.")
    proactive_score: float | None
    reactive_score: float | None
    areas_evaluated: int | None
    latitude: float | None
    longitude: float | None
    evaluations_on_record: int = Field(
        description="Evaluations of this building in the 2023-current table."
    )


class ApartmentEvaluations(BaseModel):
    latest_only: bool
    ward_filter: str | None
    address_filter: str | None
    sort: str
    total_matched: int
    returned_count: int
    offset: int
    evaluations: list[ApartmentEvaluation]
    source: DatasetSource
    provenance: Provenance


class ScoreGroup(BaseModel):
    key: str = Field(description="Ward number, property type, or 'all' for the city.")
    label: str | None = Field(description="Ward name, when grouping by ward.")
    buildings: int
    units: int = Field(description="Sum of confirmed units in those buildings.")
    mean_score: float | None
    median_score: float | None
    p25_score: float | None = Field(description="25th percentile of building scores.")
    min_score: float | None
    max_score: float | None


class ApartmentScoreSummary(BaseModel):
    group_by: Literal["ward", "property_type"]
    evaluated_since: int | None = Field(
        description="Only buildings whose latest evaluation is in this year or later."
    )
    buildings: int
    groups: list[ScoreGroup]
    city: ScoreGroup
    source: DatasetSource
    provenance: Provenance


class CountGroup(BaseModel):
    key: str
    label: str | None = Field(description="Ward name, when grouping by ward.")
    registrations: int
    share: float = Field(description="Share of all registrations, 0 to 1.")


class ShortTermRentalSummary(BaseModel):
    group_by: Literal["ward", "property_type", "postal_code"]
    registrations: int
    groups: list[CountGroup]
    source: DatasetSource
    provenance: Provenance


class Inspection(BaseModel):
    establishment_id: str | None
    establishment: str | None
    address: str | None
    inspection_date: str | None
    status: str | None = Field(description="Pass, Conditional Pass or Closed.")
    severity: str | None = Field(
        description="Of the infraction: 'M - Minor', 'S - Significant', 'C - Crucial'; "
        "'None' when the inspection found none."
    )
    infraction: str | None
    deficiency: str | None
    outcome: str | None
    outcome_date: str | None
    amount_fined: float | None
    latitude: float | None
    longitude: float | None


class InspectionSearch(BaseModel):
    establishment_filter: str | None
    address_filter: str | None
    status_filter: str | None
    total_matched: int
    returned_count: int
    offset: int
    inspections: list[Inspection]
    source: DatasetSource
    provenance: Provenance


class Councillor(BaseModel):
    role: str = Field(description="'Mayor' or 'Councillor', as published.")
    ward: str | None = Field(description="Ward number, '01' to '25'; None for the mayor.")
    ward_name: str | None = Field(description="Ward name; 'Toronto' for the mayor.")
    name: str
    email: str | None
    phone: str | None
    office_address: str | None = Field(description="City Hall office, as published.")
    website: str | None = Field(description="The member's page on toronto.ca.")


class CouncilRoster(BaseModel):
    term: str = Field(description="Council term the table covers, e.g. '2022-2026'.")
    ward_filter: str | None
    members: list[Councillor]
    source: DatasetSource
    provenance: Provenance


class WardNeighbourhood(BaseModel):
    number: str = Field(description="The City's neighbourhood number in the chosen model.")
    neighbourhood: str = Field(description="Neighbourhood name, number removed.")
    classification: str | None = Field(
        description="Toronto Strong Neighbourhoods Strategy class (NIA, Emerging, or neither)."
    )
    overlap_km2: float = Field(description="Approximate area shared with the ward, km².")
    share_of_ward: float = Field(description="Share of the ward's area in this neighbourhood.")
    share_of_neighbourhood: float = Field(
        description="Share of the neighbourhood's area inside the ward; 1.0 = wholly inside."
    )


class WardNeighbourhoods(BaseModel):
    ward: str = Field(description="Ward number, '01' to '25'.")
    ward_name: str
    neighbourhood_model: Literal[140, 158]
    ward_area_km2: float = Field(description="Approximate ward area, km² (scanline estimate).")
    min_overlap: float = Field(description="Slivers below this share of the ward are left out.")
    neighbourhoods: list[WardNeighbourhood] = Field(
        description="Neighbourhoods overlapping the ward, largest share of the ward first."
    )
    sources: list[DatasetSource]
    provenance: Provenance


class NeighbourhoodValue(BaseModel):
    number: str | None = Field(description="140-model neighbourhood number (2016 table).")
    neighbourhood: str
    value: str | None = Field(description="The value as published.")
    value_number: float | None
    parent_value_number: float | None = Field(
        description="The value of the row this one sits under, with divide_by_parent."
    )
    share: float | None = Field(description="value / parent value, 0 to 1, with divide_by_parent.")


class NeighbourhoodComparison(BaseModel):
    census_year: int
    characteristic: str = Field(description="The indicator's label, leading spaces removed.")
    topic: str | None
    row_id: int = Field(description="The row's _id in the DataStore table.")
    parent_characteristic: str | None = Field(
        description="The label of the row this one sits under (its denominator), with "
        "divide_by_parent."
    )
    data_source: str | None
    sort: str
    total_matched: int
    returned_count: int
    offset: int
    neighbourhoods: list[NeighbourhoodValue]
    city: NeighbourhoodValue
    source: DatasetSource
    provenance: Provenance


class WardScores(BaseModel):
    ward: ScoreGroup = Field(description="The ward's buildings at their latest evaluation.")
    city: ScoreGroup = Field(description="Every evaluated building in Toronto, for comparison.")
    lowest: list[ApartmentEvaluation] = Field(description="The ward's lowest-scoring buildings.")


class WardNeighbourhoodHousing(WardNeighbourhood):
    buildings_evaluated: int = Field(
        description="RentSafeTO buildings in the ward whose coordinates fall in this neighbourhood."
    )
    mean_score: float | None = Field(description="Mean latest score of those buildings.")
    renter_households: float | None = Field(description="2016 census, 25% sample.")
    private_households: float | None = Field(description="2016 census, households by tenure.")
    renter_share: float | None = Field(
        description="renter_households / private_households, 0 to 1 (2016, whole neighbourhood, "
        "including any part outside the ward)."
    )


class WardHousingProfile(BaseModel):
    ward: str = Field(description="Ward number, '01' to '25'.")
    ward_name: str
    councillor: Councillor | None
    scores: WardScores
    buildings_without_coordinates: int = Field(
        description="The ward's evaluated buildings with no coordinates, so in no neighbourhood."
    )
    neighbourhoods: list[WardNeighbourhoodHousing] = Field(
        description="140-model neighbourhoods overlapping the ward, largest share first."
    )
    city_renter_share: float | None = Field(description="Toronto's 2016 renter share, 0 to 1.")
    caveats: list[str] = Field(description="What the combination of these sources cannot show.")
    sources: list[DatasetSource] = Field(
        description="Every table used: councillors, RentSafeTO, wards, neighbourhoods, profiles."
    )
    provenance: Provenance
