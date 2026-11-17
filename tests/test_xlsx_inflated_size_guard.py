"""Every .xlsx reader refuses a workbook whose ZIP parts unpack past the limit.

shared/xlsx_sheets.check_inflated_size reads the sizes the ZIP declares before
openpyxl loads the shared strings, styles and workbook parts whole, where no parse
deadline can stop it. Eleven readers called `load_workbook` directly and skipped the
check; they now open the workbook through `open_workbook`. The limit is monkeypatched
to a few bytes so that an ordinary few-KB workbook stands in for the crafted one.
"""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from maplestats_mcp.modules.elections_provincial import manitoba, saskatchewan
from maplestats_mcp.modules.elections_results import historical
from maplestats_mcp.modules.finance_canada import client as finance_canada
from maplestats_mcp.modules.ised.ip_horizons import client as ip_horizons
from maplestats_mcp.modules.nl_stats import client as nl_stats
from maplestats_mcp.modules.oeb import records
from maplestats_mcp.modules.telecom_prices import client as telecom_prices
from maplestats_mcp.shared import xlsx_sheets
from maplestats_mcp.shared.file_download import TooLarge


def _workbook() -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Data"
    sheet.append(["Province", "Votes", "Share"])
    sheet.append(["Alberta", 10, 0.5])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


READERS = {
    "manitoba": lambda body: list(manitoba._sheets(body)),
    "saskatchewan": lambda body: saskatchewan.parse_xlsx(body),
    "elections_results": lambda body: historical._parse(body),
    "finance_canada": lambda body: finance_canada.parse_workbook(body, "en"),
    "ised_ip_horizons": lambda body: ip_horizons.parse_dictionary(body),
    "nl_stats": lambda body: nl_stats._parse_xlsx(body),
    "oeb_sheets": lambda body: records.xlsx_sheets(body),
    "oeb_records": lambda body: list(records.xlsx_records(body, "Data")),
    "telecom_prices": lambda body: telecom_prices.read_sheets(body, lambda name: True),
}


@pytest.mark.parametrize("reader", READERS.values(), ids=READERS.keys())
def test_a_workbook_over_the_unpacked_limit_is_refused_before_it_is_opened(reader, monkeypatch):
    monkeypatch.setattr(xlsx_sheets, "XLSX_MAX_PART_BYTES", 10)
    with pytest.raises(TooLarge, match="unpacks to"):
        reader(_workbook())
