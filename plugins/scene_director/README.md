# Scene director plugin (prototype, 2026-10-19)

A director agent for the scene_blender track, kept as a plugin outside `harness/` so the
harness package is untouched. Status: **implementation only — not tested and never run on a live
harness run.** Kept for later development by the owner.

## What it does

Each refine round, after the judge, one structured VLM call reads the round's own renders from the
cameras the film will use, and writes at most three *target-look* notes (what the frame shows now,
what it must look like instead), ranked by how much of the frame the target fills. The notes become
priority-1 refine tasks (`[director/direction:<kind>]`) in the harness's normal refine prompt:

| order | source | rule |
|---|---|---|
| 0 | gate ERRORs | always first; the director skips a round that has any |
| 1 | director | at most 3; protected from the task cap like gate/acceptance tasks |
| 2+ | judge improvement plan | fills what is left |

The last refine round is left to the judge alone (cleanup), following the world_demo lesson that a
large change session often leaves one interpenetration that a short follow-up fixes.

## How it hooks in (no harness edits)

`install()` wraps `SceneTrack.extra_refine_tasks`, the shared refine scaffold's existing hook
(`codeverse3d/tracks/lifecycle.py`; the static-object track uses it for reference-IoU tasks), for
the current process only. `build_refine_instructions` already protects every non-judge source from
the cap, so no core logic changes. `DirectorTask` subclasses `RefineTask` only to add the
`"director"` source label.

```bash
cd plugins/scene_director
PYTHONPATH=. python -m scene_director make "..." --track scene --language scene_blender --variant argon_raw
```

| env | default | meaning |
|---|---|---|
| `SCENE_DIRECTOR` | `1` | `0` turns it off (the hook then returns nothing) |
| `SCENE_DIRECTOR_MODEL` | run's judge backend | VLM for the director call |
| `SCENE_DIRECTOR_SHOT` | third-person follow, ~2 m, 1080p Cycles | how the scene will be filmed |
| `SCENE_DIRECTOR_VIEWS` | eye-level / route cameras from the plan | comma-separated camera names to read first |
| `SCENE_DIRECTOR_MAX_NOTES` | `3` | notes per round |
| `SCENE_DIRECTOR_SKIP_LAST` | `1` | leave the last refine round to the judge |

Per round it writes `artifacts/director/rNN.json` (views, notes, tasks, cost) and emits
`director.notes` / `director.skip` / `director.failed` events. The call goes through
`get_chat_model`, so it is metered into the run's cost ledger like any other call. A director
failure never fails a round.

## Files

- `scene_director/director.py`: config, view selection, request, notes→tasks, hook body
- `scene_director/prompts/`: director system and user prompts (tuned for argon from the w2 notes)
- `scene_director/__init__.py`: `install()` / `uninstall()`
- `scene_director/__main__.py`: `3dcode` launcher with the director installed

Written against harness commit `fc9584c9`; no tests are included (owner's choice, 2026-10-19).

## Evidence behind the design, and its limits

From the world_demo experiment (2026-10-17, `eval/bench/out/world_demo/work/w2_B` vs `w2_C`):
notes written from the delivery shot (B) changed the scene far more than handing the judge's plan to
the same agent (C); judge scores 0.960 vs 0.939. That is **one scene**, and the director there was a
person (Claude, writing notes by hand), not this automated call. Whether a VLM call reproduces those
notes is untested. 11 of 12 long `director.py` sessions timed out; this plugin instead rides the
normal refine session and budget.

## Not done (for a core merge or the next prototype step)

- A live A/B on an `eval/bench` battery: argon_raw vs argon_raw + director, paired, judged by
  `PairwiseJudge` on the delivery views (absolute scores compress above ~0.9), plus timeout rate
  and cost.
- Telling the judge the director's targets (`ScenePipeline.judge_context`): it changes the judge
  payload, so old scores would stop being comparable.
- Real delivery-shot renders (a follow camera along the route) instead of the plan's eye-level
  cameras.
- Core merge path: `"director"` in `RefineTask.source`, a `director` Settings flag and variant knob,
  the templates under `prompts/` (variant-overridable), and this hook body in `tracks/`.
