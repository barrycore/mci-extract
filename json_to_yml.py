import json
import yaml
from pathlib import Path

input_path = Path("input.json")
output_path = Path("output.yml")

with input_path.open() as f:
    data = json.load(f)

with output_path.open("w") as f:
    yaml.safe_dump(data, f, sort_keys=False)

print("Converted JSON → YAML")