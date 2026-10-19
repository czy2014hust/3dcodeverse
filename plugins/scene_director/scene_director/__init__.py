"""Scene director plugin for the 3dcodeverse harness — a prototype kept outside the main repository.

``install()`` binds the director onto ``SceneTrack.extra_refine_tasks`` (the scaffold's existing hook,
``tracks/lifecycle.py``) for this process only.  No harness file is edited; ``uninstall()`` restores
the original method.  Run a harness command with it active via ``python -m scene_director <3dcode args>``.
"""

from __future__ import annotations

from typing import Any

_ORIGINAL: Any = None


def install() -> None:
    global _ORIGINAL
    from codeverse3d.tracks.scene import SceneTrack

    from scene_director.director import director_refine_tasks

    if _ORIGINAL is not None:
        return
    _ORIGINAL = SceneTrack.extra_refine_tasks

    def extra_refine_tasks(self: Any, ctx: Any, last: Any) -> list[Any]:
        return [*_ORIGINAL(self, ctx, last), *director_refine_tasks(self, ctx, last)]

    SceneTrack.extra_refine_tasks = extra_refine_tasks  # type: ignore[method-assign]


def uninstall() -> None:
    global _ORIGINAL
    from codeverse3d.tracks.scene import SceneTrack

    if _ORIGINAL is not None:
        SceneTrack.extra_refine_tasks = _ORIGINAL  # type: ignore[method-assign]
        _ORIGINAL = None


__all__ = ["install", "uninstall"]
