import yaml
from pathlib import Path

REG_PATH = Path("/app/configs/tool_registry.yaml")

def load_registry() -> list[dict]:
    data = yaml.safe_load(REG_PATH.read_text(encoding="utf-8"))
    return data["servers"]
