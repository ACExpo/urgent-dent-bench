from pathlib import Path
import json

REQUIRED = {"case_id", "source_type", "domain", "variant", "vignette"}

def load_jsonl(path):
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            missing = REQUIRED - row.keys()
            if missing:
                raise ValueError(f"{path}:{line_no}: missing {sorted(missing)}")
            yield row
