"""Mark the steps of a plan that sit on a host blocking automated clients, and say what works.

On 2026-11-17 StatCan's www150 host began answering every automated client with a Cloudflare
challenge, and a plan for "Alberta's unemployment rate" still sent the model to
`wds_search_cubes` and `wds_get_cube_metadata`, which could only fail. The breaker
(shared/breaker.py) knows which hosts answer with a challenge; this reads it and, for each
step whose tool needs such a host (shared/blocked_hosts.py), keeps the step but

- sets `blocked: true` and drops its `call` (nothing to pass to a tool that cannot answer),
- ends its purpose with a one-line note,
- lists it after the steps on hosts that work, in the same list.

A topic that still has steps on other hosts gets one caveat naming up to four of them, taken
from the topic's own steps (nothing is invented), and the plan gets one line of guidance
first: which host, since when, do not call or retry, and the sources that still answer.

It runs last, after the French is chosen, because the French step purposes are looked up by
their exact English text and a purpose with a note on it would not be found. With no host
blocked, or none that a step needs, the plan is returned untouched: not one byte differs.
tests/test_planner_blocked.py checks that, in both languages, and the size of a blocked plan.
"""

from __future__ import annotations

from maplestats_mcp.modules.planner.schemas import BlockedStep, QueryPlan, StepOut
from maplestats_mcp.shared import host_health
from maplestats_mcp.shared.blocked_hosts import still_working_short
from maplestats_mcp.shared.breaker import HostBlock
from maplestats_mcp.shared.i18n import french_text

# Steps named in a topic's "reachable now" caveat; the plan is read again at every later
# step, so the line stays short.
MAX_NAMED = 4


def _blocked_step(step: StepOut, block: HostBlock, french: bool) -> BlockedStep:
    return BlockedStep(
        tool=step.tool,
        purpose=host_health.step_purpose(block, french=french),
    )


def _sorted(
    steps: list[StepOut], blocked: dict[str, HostBlock], french: bool, hit: dict[str, HostBlock]
) -> tuple[list[StepOut], list[StepOut]]:
    """The steps with the blocked ones last, and the steps that work."""
    working: list[StepOut] = []
    stuck: list[StepOut] = []
    for step in steps:
        block = host_health.block_of(step.tool, blocked)
        if block is None:
            working.append(step)
        else:
            hit[block.host] = block
            stuck.append(_blocked_step(step, block, french))
    return [*working, *stuck], working


def _reachable(working: list[StepOut], french: bool) -> str:
    listed = ", ".join(dict.fromkeys(step.tool for step in working[:MAX_NAMED]))
    return f"Accessibles maintenant : {listed}." if french else f"Reachable now: {listed}."


def _guidance(hit: dict[str, HostBlock], french: bool) -> str:
    hosts = sorted(hit)
    since = host_health.since_text(hit[hosts[0]], french=french)
    works = still_working_short(hosts[0], french)
    names = ", ".join(hosts)
    if french:
        return french_text(
            f"Bloqué maintenant : {names}{since} bloque les clients automatisés. N'appelez ni "
            "ne réessayez les étapes marquées blocked ; si rien d'autre ne répond, dites que "
            f"le chiffre n'a pas pu être lu à la source.{works}"
        )
    return (
        f"Blocked now: {names}{since} is challenging automated clients. Do not call or retry "
        "the steps marked blocked; if nothing else answers, say the figure could not be read "
        f"from its source.{works}"
    )


def mark_blocked(plan: QueryPlan, french: bool) -> QueryPlan:
    """`plan` with its steps on a blocked host marked and last, or `plan` itself when none."""
    blocked = host_health.blocked_now()
    if not blocked:
        return plan
    hit: dict[str, HostBlock] = {}
    for topic in plan.topics:
        topic.steps, working = _sorted(topic.steps, blocked, french, hit)
        if working and len(working) < len(topic.steps):
            topic.caveats.insert(0, _reachable(working, french))
    for place in plan.places:
        place.steps, _ = _sorted(place.steps, blocked, french, hit)
    plan.fallback_steps, _ = _sorted(plan.fallback_steps, blocked, french, hit)
    if hit:
        plan.guidance.insert(0, _guidance(hit, french))
    return plan
