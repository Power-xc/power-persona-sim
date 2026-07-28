"""dataset — HF 로딩, DuckDB 원격 쿼리, 캐시 관리, 스키마 검증."""

from .cache import apply_hf_home, resolve_hf_home
from .schema import (
    LIST_COLUMNS,
    SchemaError,
    parse_list_field,
    to_persona_record,
    to_persona_records,
    validate_schema,
)
from .sources import (
    HF_PARQUET_GLOB,
    SHARD_COUNT,
    DuckDBRemoteSource,
    FixtureSource,
    HFDatasetsSource,
    ParquetShardSource,
    PersonaSource,
    build_remote_query,
    get_source,
    read_jsonl,
    shard_uri,
    write_jsonl,
)

__all__ = [
    "HF_PARQUET_GLOB",
    "LIST_COLUMNS",
    "SHARD_COUNT",
    "DuckDBRemoteSource",
    "FixtureSource",
    "HFDatasetsSource",
    "ParquetShardSource",
    "PersonaSource",
    "SchemaError",
    "apply_hf_home",
    "build_remote_query",
    "get_source",
    "parse_list_field",
    "read_jsonl",
    "resolve_hf_home",
    "shard_uri",
    "to_persona_record",
    "to_persona_records",
    "validate_schema",
    "write_jsonl",
]
