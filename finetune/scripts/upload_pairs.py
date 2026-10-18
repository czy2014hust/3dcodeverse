"""Compatibility CLI; the implementation lives in finetune/llamafactory/."""

import runpy
import sys
from pathlib import Path


def main():
    scripts = Path(__file__).resolve().parents[1] / "llamafactory"
    sys.path.insert(0, str(scripts))
    runpy.run_path(str(scripts / Path(__file__).name), run_name="__main__")


if __name__ == "__main__":
    main()
