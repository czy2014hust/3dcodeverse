"""``python -m scene_director make "..." --track scene --language scene_blender --variant argon_raw``

Same arguments as ``3dcode``; the director is installed for this process first."""

from scene_director import install

install()

from codeverse3d.cli.main import app  # noqa: E402

app(prog_name="3dcode+director")
