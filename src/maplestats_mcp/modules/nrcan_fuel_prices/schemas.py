"""Typed responses for NRCan's average retail fuel prices by city."""

from __future__ import annotations

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance


class FuelProduct(BaseModel):
    product: str = Field(description="Pass to nrcan_fuel_prices_get_prices (or its name).")
    name: str


class FuelLocation(BaseModel):
    location: str = Field(description="NRCan's location id; the name works too.")
    name: str


class FuelCatalogue(BaseModel):
    products: list[FuelProduct]
    frequencies: list[str] = Field(description="daily, weekly or monthly.")
    years: list[int] = Field(description="Years with weekly and monthly averages.")
    locations: list[FuelLocation]
    note: str
    provenance: Provenance


class FuelPrice(BaseModel):
    period: str = Field(
        description="The day (daily), the week's last day, a Tuesday (weekly), or YYYY-MM."
    )
    location: str
    price: float | None = Field(description="Average retail price, taxes included (¢/L).")
    taxes: float | None = Field(description="Taxes in the price (¢/L).")
    marketing_margin: float | None = Field(description="Retail minus wholesale, before tax.")
    refining_margin: float | None = Field(
        description="Wholesale minus NRCan's crude oil estimate. Blank on the latest day."
    )


class FuelPrices(BaseModel):
    product: str
    product_name: str
    frequency: str = Field(
        description="The frequency NRCan served, which can differ from the one asked (see `note`)."
    )
    note: str | None = None
    year: int | None = Field(description="The year asked for; None for daily prices.")
    unit: str
    locations: list[str]
    rows: list[FuelPrice] = Field(description="Oldest first.")
    total_rows: int = Field(description="Rows in NRCan's table before latest_n.")
    title: str
    source_url: str
    provenance: Provenance
