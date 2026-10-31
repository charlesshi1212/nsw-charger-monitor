# USYD CODE CITATION ACKNOWLEDGEMENT
# I declare that this file was developed with extensive assistance from OpenAI Codex.
# The submitting team must review, understand and verify the implementation.
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / 'database/ev_stream.duckdb'
DEFAULT_TOPIC = 'comp5339/TUT06-08/events'


def read_jsonl(path):
    with Path(path).open(encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)
