"""Validate the benchmark case shards; the checks live in urgentdentbench.validation."""
import sys
from pathlib import Path

from urgentdentbench.validation import main

if __name__ == "__main__":
    sys.exit(main(Path(__file__).resolve().parents[1]))
