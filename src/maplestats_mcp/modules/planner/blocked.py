"""Mark the steps of a plan that sit on a StatCan path answering with the bot check.

StatCan answers scripts with a Cloudflare check on some paths and not on others (shared/
challenge_notes.py lists them; WDS answers, SDMX and the CIMT trade API do not), so a plan
that sends the model to `cimt_get_trade` can only cost it a failed call before the error's
note names the route that works. shared/path_health.py remembers which paths this server met
the check on in the last 15 minutes, from real calls and from statcan_check_access. For a
step whose tool has no other route on such a path (path_health.DEPENDENCIES) this keeps the
step but

- marks it `blocked: true`, drops its `call` and shortens its purpose to a note,
- lists it after the steps that work, in the same list, and
- puts the nearest working route first in its topic (the same data through WDS, labelled as
  that route), unless the topic already has that tool.

It runs last, after the French is chosen, because
the French step purposes are looked up by their exact English text. It reads only what the
calls already saw and sends nothing: no request, no probe. With no path challenged, or none
a step needs, the plan is returned untouched, byte for byte; tests/test_planner_blocked.py
checks that over every benchmark question, and the size of a plan with the paths blocked.
"""

from __future__ import annotations

from maplestats_mcp.modules.planner import calls
from maplestats_mcp.modules.planner.schemas import BlockedStep, QueryPlan, StepOut
from maplestats_mcp.modules.planner.topics import PlanStep
from maplestats_mcp.shared import path_health
from maplestats_mcp.shared.i18n import french_text
from maplestats_mcp.shared.path_health import Dependency

# The nearest working route for each dependency, as a step: the same data through WDS. The
# tables are the ones shared/challenge_notes.py names for the CIMT trade API; none is invented.
ROUTES: dict[str, PlanStep] = {
    "cimt": PlanStep(
        "wds_get_cube_metadata",
        "WDS, as StatCan's CIMT API is blocked: table 12-10-0011-01 (partners, monthly) or "
        "12-10-0163-01 (by product), no HS detail",
        args=(("product_id", "12-10-0011-01"),),
    ),
    "pages": PlanStep(
        "wds_search_cubes",
        "WDS, as StatCan's catalogue pages are blocked: tables by words in their titles",
    ),
}
ROUTES_FR: dict[str, str] = {
    "cimt": (
        "WDS, l'API CICM de StatCan étant bloquée : tableau 12-10-0011-01 (partenaires, "
        "mensuel) ou 12-10-0163-01 (par produit), sans détail du SH"
    ),
    "pages": (
        "WDS, les pages du catalogue de StatCan étant bloquées : tableaux par les mots de "
        "leur titre"
    ),
}


def _blocked_step(step: StepOut, dependency: Dependency, french: bool) -> BlockedStep:
    note = (
        f"bloqué ({dependency.label_fr}) : ne pas appeler"
        if french
        else f"blocked ({dependency.label_en}): do not call"
    )
    return BlockedStep(tool=step.tool, purpose=french_text(note) if french else note)


def _sorted(
    steps: list[StepOut],
    challenged: frozenset[str],
    french: bool,
    hit: dict[str, Dependency],
    add_route: bool,
) -> list[StepOut]:
    """`steps` with the blocked ones last, and the working route first when it is missing."""
    working: list[StepOut] = []
    stuck: list[StepOut] = []
    blocking: list[Dependency] = []
    for step in steps:
        dependency = path_health.dependency_blocking(step.tool, challenged)
        if dependency is None:
            working.append(step)
        else:
            hit[dependency.key] = dependency
            blocking.append(dependency)
            stuck.append(_blocked_step(step, dependency, french))
    routes: list[StepOut] = []
    present = {step.tool for step in steps}
    for dependency in dict.fromkeys(blocking if add_route else []):
        plan_step = ROUTES[dependency.key]
        if plan_step.tool in present:
            continue
        present.add(plan_step.tool)
        purpose = french_text(ROUTES_FR[dependency.key]) if french else plan_step.purpose
        routes.append(StepOut(tool=plan_step.tool, purpose=purpose, call=calls.call_for(plan_step)))
    return [*routes, *working, *stuck]


def mark_blocked(plan: QueryPlan, french: bool) -> QueryPlan:
    """`plan` with its steps on a challenged path marked and last, or `plan` itself when none."""
    challenged = path_health.challenged_now()
    if not challenged:
        return plan
    hit: dict[str, Dependency] = {}
    for topic in plan.topics:
        topic.steps = _sorted(topic.steps, challenged, french, hit, add_route=True)
    for place in plan.places:
        place.steps = _sorted(place.steps, challenged, french, hit, add_route=False)
    plan.fallback_steps = _sorted(plan.fallback_steps, challenged, french, hit, add_route=False)
    return plan
