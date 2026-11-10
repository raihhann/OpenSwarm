"""Repository test imports; no installed package or physical hardware required."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "master", ROOT / "slaves/linux", ROOT / "projects/hydra_arm/master"):
    sys.path.insert(0, str(directory))
