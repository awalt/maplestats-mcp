"""Argument names a model often guesses, read as the real ones before a tool validates them.

Tools name the same idea differently (`series_names` on boc_get_observations,
`noc` on jobbank_get_wages, `rows` on ckan_search_datasets), and the first call
from a model that has not read the schema fails validation (issue #273: 5 of
about 30 first calls in one review session). The error names the field and
gives the schema, so each cost one more round trip, but a smaller model may
not recover.

call_tool reads a guessed name as the real one for the few cases below, and the
result says so (a caveat in its provenance), so the next call can use the real
name. Deliberately narrow:

- the table is per tool, never a global rename, and no tool's published
  signature changes;
- an alias is read only when the tool has no parameter of that name and does
  have the real one, so a tool that later gains a `limit` keeps it;
- a caller's own argument is never overridden: when both names are given
  nothing is mapped and validation reports them as it always did;
- a tool that is not in the table is untouched.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from maplestats_mcp.shared.i18n import pick


@dataclass(frozen=True)
class Alias:
    """The real parameter a guessed name stands for."""

    real: str
    # The real parameter takes a list and the guess is often one bare string.
    as_list: bool = False


@dataclass(frozen=True)
class Mapped:
    """One alias read as its real argument in one call."""

    alias: str
    real: str
    wrapped: bool

    def note(self, lang: str | None) -> str:
        """The sentence that tells the caller which name to use next time."""
        en = f"Argument `{self.alias}` was read as `{self.real}`"
        fr = f"L'argument `{self.alias}` a été lu comme `{self.real}`"
        if self.wrapped:
            en += " (a single value was put in a list)"
            fr += " (une valeur unique a été placée dans une liste)"
        return pick(
            lang,
            f"{en}; use `{self.real}` next time. MapleStats reads only a few common "
            "alternative names, not every one.",
            f"{fr} ; utilisez `{self.real}` la prochaine fois. MapleStats ne reconnaît "
            "que quelques noms alternatifs courants, pas tous.",
        )


# Tool name -> guessed argument name -> the real one. Each entry was a real first-call
# failure (issue #273); add one only for a guess that means exactly the real argument.
# `series` is the name of boc_get_observations' output field, `noc_code` of
# jobbank_get_wages', and `limit` is the row count on most other tools.
ARGUMENT_ALIASES: dict[str, dict[str, Alias]] = {
    "boc_get_observations": {"series": Alias("series_names", as_list=True)},
    "jobbank_get_wages": {"noc_code": Alias("noc")},
    "ckan_search_datasets": {"limit": Alias("rows")},
}


def apply_aliases(
    tool: str, parameters: Collection[str], arguments: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, list[Mapped]]:
    """`arguments` with the aliases of `tool` read as real names, and what was mapped.

    `parameters` are the tool's real parameter names. Returns `arguments` itself
    and no mappings when nothing applies; otherwise a new dict, in which a mapped
    argument keeps the position of the alias it replaces.
    """
    table = ARGUMENT_ALIASES.get(tool)
    if not table or not arguments:
        return arguments, []
    renames = {
        alias: spec
        for alias, spec in table.items()
        if alias in arguments
        and spec.real not in arguments
        and alias not in parameters
        and spec.real in parameters
    }
    if not renames:
        return arguments, []
    mapped: list[Mapped] = []
    result: dict[str, Any] = {}
    for key, value in arguments.items():
        spec = renames.get(key)
        if spec is None:
            result[key] = value
            continue
        wrapped = spec.as_list and isinstance(value, str)
        result[spec.real] = [value] if wrapped else value
        mapped.append(Mapped(alias=key, real=spec.real, wrapped=wrapped))
    return result, mapped
