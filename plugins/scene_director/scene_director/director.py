"""The art director: shot-view notes that become priority-1 refine tasks on the scene track.

One structured VLM call per refine round.  It looks at the views the film will actually use (the
round's own authored renders — nothing is rendered for it), writes at most ``max_notes`` target-look
notes ranked by screen share, and hands them to the shared refine scaffold through
``extra_refine_tasks``.  Gate ERRORs still come first (priority 0); the judge's plan fills what is left.

Lessons it encodes (world_demo, 2026-10-17, one scene — see ../README.md):
* notes written from the delivery shot changed far more than the judge's plan did (judge 0.939 vs 0.960
  on the same scene, the visual gap much larger): the judge saturates above ~0.9;
* a long "big change" session tended to time out with one interpenetration left: so few notes per
  round, never on a round with gate ERRORs, and the last refine round is the judge's alone (cleanup).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from codeverse3d.contracts.chat import ImagePart
from codeverse3d.contracts.plan import ScenePlan
from codeverse3d.models import get_chat_model
from codeverse3d.models.schema_utils import ask_structured
from codeverse3d.orchestrator import RefineTask

log = logging.getLogger(__name__)

PROMPTS = Path(__file__).with_name("prompts")
#: words in a camera's name / purpose that mark a delivery (eye-level, along-the-route) view
SHOT_WORDS = ("eye", "trail", "walk", "route", "path", "hero", "street", "ground", "follow", "approach")
DEFAULT_SHOT = ("a third-person camera about 2 m up and 3–4 m behind a character walking the main route, "
                "rendered in Cycles at 1920x1080")


class DirectorTask(RefineTask):
    """A ``RefineTask`` from the director.  Same fields; only the source label is new, so the
    scaffold's cap keeps it (it protects every non-judge source) and ``line()`` prints
    ``[director/<kind>]``.  A core merge would add ``"director"`` to ``RefineTask.source`` instead."""

    source: Literal["gate", "acceptance", "judge", "director"] = "director"  # type: ignore[assignment]


class DirectorNote(BaseModel):
    target: str = Field(description="a zone or asset name from the plan, or 'environment'")
    view: str = Field(description="the camera the note is read from")
    screen_share: float = Field(ge=0.0, le=1.0, description="rough fraction of that frame the target fills")
    kind: Literal["geometry", "material", "lighting", "atmosphere", "dressing", "motion"]
    now: str = Field(description="what the frame shows today, in visible terms")
    target_look: str = Field(description="what it must look like instead: concrete, visible features")


class DirectorNotes(BaseModel):
    read: str = Field(description="two sentences: what the shot is and what most weakens it")
    notes: list[DirectorNote] = Field(default_factory=list)


class DirectorConfig(BaseModel):
    """Read from ``SCENE_DIRECTOR_*`` (not ``C3D_*``: the plugin adds no harness Settings field)."""

    enabled: bool = True
    model: str = ""            # "" → the run's judge backend
    shot: str = DEFAULT_SHOT   # how the scene will be filmed
    views: list[str] = Field(default_factory=list)   # camera names; [] → picked from the plan
    max_notes: int = 3
    max_images: int = 4
    skip_last_round: bool = True

    @classmethod
    def from_env(cls) -> DirectorConfig:
        e = os.environ.get
        return cls(enabled=e("SCENE_DIRECTOR", "1") not in ("0", "false", "off", ""),
                   model=e("SCENE_DIRECTOR_MODEL", ""),
                   shot=e("SCENE_DIRECTOR_SHOT", DEFAULT_SHOT),
                   views=[v.strip() for v in e("SCENE_DIRECTOR_VIEWS", "").split(",") if v.strip()],
                   max_notes=int(e("SCENE_DIRECTOR_MAX_NOTES", "3")),
                   max_images=int(e("SCENE_DIRECTOR_MAX_IMAGES", "4")),
                   skip_last_round=e("SCENE_DIRECTOR_SKIP_LAST", "1") not in ("0", "false", "off"))


def skip_reason(ctx: Any, last: Any, cfg: DirectorConfig) -> str:
    """Why the director sits this round out ("" = it runs)."""
    if not cfg.enabled:
        return "disabled"
    if not isinstance(ctx.plan, ScenePlan) or ctx.language.value != "scene_blender":
        return "not a scene_blender run"
    if last.renders is None or not last.renders.views:
        return "no renders"
    if any(g.errors for g in last.gates):
        return "gate errors first"
    if cfg.skip_last_round and last.index + 1 >= ctx.policy.max_rounds:
        return "last refine round is the judge's (cleanup)"
    return ""


def delivery_views(ctx: Any, last: Any, cfg: DirectorConfig) -> list[Any]:
    """The round's renders the film would use: named cameras first, then eye-level / route cameras by
    their plan purpose, then every other authored camera; the first animation time of each."""
    plan: ScenePlan = ctx.plan
    authored = {c.name: c for c in plan.cameras}
    by_cam: dict[str, Any] = {}
    for v in sorted(last.renders.views, key=lambda v: v.time_s or 0.0):
        cam = next((n for n in authored if v.name == n or v.name.startswith(f"{n}_")), None)
        if cam and cam not in by_cam and v.mode == "shaded":
            by_cam[cam] = v

    def rank(name: str) -> tuple[int, int]:
        if name in cfg.views:
            return (0, cfg.views.index(name))
        text = f"{name} {authored[name].purpose}".lower()
        return (1 if any(w in text for w in SHOT_WORDS) else 2, 0)

    return [by_cam[n] for n in sorted(by_cam, key=rank)][:cfg.max_images]


def _known_targets(plan: ScenePlan) -> list[str]:
    return [z.name for z in plan.zones] + [a.name for a in plan.assets] + ["environment"]


def build_request(ctx: Any, last: Any, views: list[Any], cfg: DirectorConfig) -> tuple[str, str, list[ImagePart]]:
    plan: ScenePlan = ctx.plan
    judged = ""
    if last.judgment is not None:
        judged = "\n".join(f"- [{i.severity}] {i.target}: {i.detail}" for i in last.judgment.issues[:8])
    user = (PROMPTS / "director_user.md").read_text().format(
        prompt=ctx.spec.prompt.strip(), shot=cfg.shot, title=plan.title, setting=plan.setting, mood=plan.mood,
        environment=plan.environment[:1500],
        zones="\n".join(f"- {z.name}: {', '.join(z.contents)}" for z in plan.zones),
        targets=", ".join(_known_targets(plan)),
        views="\n".join(f"- {v.name}: {next((c.purpose for c in plan.cameras if v.name.startswith(c.name)), '')}"
                        for v in views),
        judged=judged or "(none)", max_notes=cfg.max_notes)
    system = (PROMPTS / "director_system.md").read_text()
    images = [ImagePart(path=v.path, label=v.name) for v in views]
    return system, user, images


def notes_to_tasks(notes: DirectorNotes, plan: ScenePlan, file_for_target: Any, max_notes: int) -> list[DirectorTask]:
    """Keep notes on known targets, largest screen share first, at most ``max_notes``."""
    known = {t.lower(): t for t in _known_targets(plan)}
    kept = sorted((n for n in notes.notes if n.target.lower() in known), key=lambda n: -n.screen_share)[:max_notes]
    out = []
    for n in kept:
        target = known[n.target.lower()]
        out.append(DirectorTask(
            target=target, kind=f"direction:{n.kind}", priority=1,
            instruction=(f"In {n.view} (≈{n.screen_share:.0%} of the frame) it reads as: {n.now}  "
                         f"Make it read as: {n.target_look}  One change at a time; build after each."),
            files=[] if target == "environment" else list(file_for_target(target))))
    return out


def director_refine_tasks(track: Any, ctx: Any, last: Any, cfg: DirectorConfig | None = None,
                          model: Any = None) -> list[DirectorTask]:
    """The hook body.  Never raises: a director failure is logged and the round runs on the judge alone."""
    cfg = cfg or DirectorConfig.from_env()
    why = skip_reason(ctx, last, cfg)
    if why:
        ctx.events.emit("director.skip", round=last.index + 1, reason=why)
        return []
    try:
        views = delivery_views(ctx, last, cfg)
        if not views:
            ctx.events.emit("director.skip", round=last.index + 1, reason="no authored shaded views")
            return []
        system, user, images = build_request(ctx, last, views, cfg)
        model = model or get_chat_model(cfg.model or ctx.spec.backends.judge)
        notes, usage, error = ask_structured(model, DirectorNotes, system=system, text=user, images=images,
                                             temperature=0.4, label="director")
        if notes is None:
            ctx.events.emit("director.failed", round=last.index + 1, error=error[:300])
            return []
        tasks = notes_to_tasks(notes, ctx.plan, track.refine_file_for_target(ctx), cfg.max_notes)
        out = Path(ctx.ws.artifacts) / "director" / f"r{last.index + 1:02d}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"views": [v.name for v in views], "notes": notes.model_dump(mode="json"),
                                   "tasks": [t.line() for t in tasks], "cost_usd": usage.cost_usd,
                                   "config": cfg.model_dump(mode="json")}, indent=1, ensure_ascii=False))
        ctx.events.emit("director.notes", round=last.index + 1, n=len(tasks), views=[v.name for v in views],
                        cost_usd=round(usage.cost_usd, 5))
        return tasks
    except Exception as e:  # noqa: BLE001 — the director is advisory; it must never kill a round
        log.warning("director failed: %s: %s", type(e).__name__, e)
        ctx.events.emit("director.failed", round=last.index + 1, error=f"{type(e).__name__}: {e}"[:300])
        return []
