"""Mem0 2.x configuration for the plan store.

All state for a target lives in a data folder **next to the target file**, mirroring
the predecessor's convention: a prove target `…/Main.lean` keeps everything in
`…/Main_data/` (graph + statements.json + progress.json + analytics.json). Nothing is
stored inside the plan_store package itself.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Disable telemetry before importing mem0 (flag is read at import time).
os.environ.setdefault("MEM0_TELEMETRY", "False")


def _load_api_key() -> None:
    """Find the OpenAI key: an env var already set, else the nearest `.env`
    walking up from this file (e.g. the shared `.env`)."""
    if os.getenv("OPENAI_API_KEY"):
        return
    here = Path(__file__).resolve()
    for p in [here.parent, *here.parents]:
        cand = p / ".env"
        if cand.exists():
            load_dotenv(cand)
            if os.getenv("OPENAI_API_KEY"):
                return


_load_api_key()

from mem0 import Memory  # noqa: E402  (after telemetry flag + .env)

LLM_MODEL = os.getenv("PLAN_LLM_MODEL", "gpt-4o-mini")

# Embeddings default to text-embedding-3-large at its native 3072 dims.
#
# NOTE: the embedding model and its dimension are baked into each Qdrant collection at
# creation time, and vectors from different models are not comparable. Changing either
# means re-embedding an existing store:
#     cli.py --data D export-json --out plan.json && cli.py --data D reset \
#         && cli.py --data D import-json plan.json
# Keeping the native 3072 dims (rather than reducing to 1536) is deliberate: a store built
# by an older 1536-dim model then fails loudly on dimension mismatch instead of silently
# mixing incompatible vectors.
EMBED_MODEL = os.getenv("PLAN_EMBED_MODEL", "text-embedding-3-large")
EMBED_DIMS = int(os.getenv("PLAN_EMBED_DIMS", "3072"))
COLLECTION = "plan"
SCOPE = "plan"  # single Mem0 user_id per data folder (each folder is one isolated store)


def get_data_dir(target) -> Path:
    """Resolve the data folder for a target, next to it (predecessor convention).

    - a `.lean` file  → `<file.parent>/<file.stem>_data/`
    - a directory     → legacy `<dir>/datas/` if present, else `<dir>/<dir.name>_data/`
    - a folder already ending in `_data`/named `datas` → used as-is
    """
    target = Path(target)
    if target.name == "datas" or target.name.endswith("_data"):
        return target
    if target.suffix == ".lean" or (target.exists() and target.is_file()):
        return target.parent / f"{target.stem}_data"
    legacy = target / "datas"
    if legacy.exists():
        return legacy
    return target / f"{target.name}_data"


def build_memory_config(data_dir) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or set the env var.")
    data_dir = Path(data_dir)
    qdrant_path = data_dir / "qdrant"
    qdrant_path.mkdir(parents=True, exist_ok=True)
    return {
        "llm": {"provider": "openai", "config": {"model": LLM_MODEL, "temperature": 0.0}},
        "embedder": {"provider": "openai", "config": {"model": EMBED_MODEL, "embedding_dims": EMBED_DIMS}},
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": COLLECTION,
                "embedding_model_dims": EMBED_DIMS,
                "path": str(qdrant_path),
                "on_disk": True,
            },
        },
        "history_db_path": str(data_dir / "history.db"),
        "version": "v1.1",
    }


def get_plan_memory(data_dir) -> Memory:
    return Memory.from_config(build_memory_config(data_dir))
