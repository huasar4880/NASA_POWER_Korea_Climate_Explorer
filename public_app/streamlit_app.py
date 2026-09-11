"""Community Cloud entrypoint: public mode only, regardless of environment configuration."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from public_app.app import run

run()
