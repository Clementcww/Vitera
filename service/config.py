from pathlib import Path
from functools import cache
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@cache
def config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())
