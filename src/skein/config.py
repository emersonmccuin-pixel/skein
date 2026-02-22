from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULTS = {
    "db_path": "./skein.db",
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "wcp_data_path": "",
}


@dataclass
class SkeinConfig:
    db_path: str = DEFAULTS["db_path"]
    embedding_model: str = DEFAULTS["embedding_model"]
    wcp_data_path: str = DEFAULTS["wcp_data_path"]

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> SkeinConfig:
        """Load config from YAML file, falling back to defaults."""
        data: dict = {}
        if config_path:
            path = Path(config_path)
            if path.exists():
                data = yaml.safe_load(path.read_text()) or {}
        else:
            # Look for skein.yaml in current dir
            local = Path("skein.yaml")
            if local.exists():
                data = yaml.safe_load(local.read_text()) or {}

        return cls(
            db_path=data.get("db_path", DEFAULTS["db_path"]),
            embedding_model=data.get("embedding_model", DEFAULTS["embedding_model"]),
            wcp_data_path=data.get("wcp_data_path", DEFAULTS["wcp_data_path"]),
        )
