#!/usr/bin/env python3
import argparse
import json
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import psycopg
from psycopg.rows import dict_row


@dataclass
class DbConfig:
    dsn: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate rows from a source Postgres table to a destination Postgres table, preserving UUIDs and best-effort field mapping."
    )
    parser.add_argument(
        "--source-dsn",
        default=os.environ.get("SOURCE_DB_DSN"),
        help="Source Postgres DSN. Can also be set via SOURCE_DB_DSN env var.",
    )
    parser.add_argument(
        "--dest-dsn",
        default=os.environ.get("DEST_DB_DSN"),
        help="Destination Postgres DSN. Can also be set via DEST_DB_DSN env var.",
    )
    parser.add_argument(
        "--source-table",
        default=os.environ.get("SOURCE_TABLE", "artwork_artwork"),
        help="Source table name (optionally schema-qualified). Default: artwork_artwork",
    )
    parser.add_argument(
        "--dest-table",
        default=os.environ.get("DEST_TABLE"),
        required=False,
        help="Destination table name (optionally schema-qualified). If omitted, defaults to the source table name.",
    )
    parser.add_argument(
        "--id-column",
        default=os.environ.get("ID_COLUMN", "id"),
        help="Name of the primary key/UUID column used for conflict handling. Default: id",
    )
    parser.add_argument(
        "--exclude-columns",
        default=os.environ.get("EXCLUDE_COLUMNS", "order_id"),
        help="Comma-separated list of source columns to exclude from migration. Default: order_id",
    )
    parser.add_argument(
        "--column-map",
        default=os.environ.get("COLUMN_MAP"),
        help=(
            "JSON string or path to a JSON file mapping source->dest columns. "
            'Example: \'{"created_at":"created_at","price_cents":"price_cents"}\''
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("BATCH_SIZE", "500")),
        help="Number of rows to migrate per batch. Default: 500",
    )
    parser.add_argument(
        "--where",
        default=os.environ.get("WHERE"),
        help="Optional SQL WHERE clause (without the WHERE keyword) to limit source rows.",
    )
    parser.add_argument(
        "--on-conflict",
        choices=["skip", "update", "error"],
        default=os.environ.get("ON_CONFLICT", "skip"),
        help="Conflict behavior on duplicate id. 'skip' uses DO NOTHING, 'update' upserts, 'error' raises. Default: skip",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If set, no changes will be written to the destination. Useful for preview.",
    )
    return parser.parse_args()


def load_column_map(value: Optional[str]) -> Dict[str, str]:
    if not value:
        return {}
    # If value is a path to a file, try loading it; otherwise parse as JSON string
    if os.path.exists(value):
        with open(value, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse --column-map as JSON: {exc}") from exc


def normalize_table_name(table: str) -> Tuple[Optional[str], str]:
    """
    Returns (schema, table). If schema not provided, returns (None, table).
    """
    parts = table.split(".")
    if len(parts) == 1:
        return None, parts[0]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise ValueError(f"Invalid table name: {table}")


def fetch_columns(conn: psycopg.Connection, table: str) -> List[str]:
    schema, relname = normalize_table_name(table)
    if schema is None:
        schema = "public"
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = %s and table_name = %s
            order by ordinal_position
            """,
            (schema, relname),
        )
        rows = cur.fetchall()
    return [r[0] for r in rows]


def fetch_primary_key_columns(conn: psycopg.Connection, table: str) -> List[str]:
    schema, relname = normalize_table_name(table)
    if schema is None:
        schema = "public"
    with conn.cursor() as cur:
        cur.execute(
            """
            select a.attname as column_name
            from pg_index i
            join pg_class c on c.oid = i.indrelid
            join pg_namespace n on n.oid = c.relnamespace
            join pg_attribute a on a.attrelid = c.oid and a.attnum = any(i.indkey)
            where i.indisprimary = true
              and n.nspname = %s
              and c.relname = %s
            """,
            (schema, relname),
        )
        rows = cur.fetchall()
    return [r[0] for r in rows]


def build_mapping(
    source_columns: Sequence[str],
    dest_columns: Sequence[str],
    explicit_map: Dict[str, str],
    excludes: Iterable[str],
) -> Dict[str, str]:
    """
    Compute source->dest column mapping. Start with explicit_map, then map same-name columns,
    skipping excluded columns and those not present in destination.
    """
    exclude_set = {c.strip() for c in excludes if c and c.strip()}
    dest_set = set(dest_columns)
    mapping: Dict[str, str] = {}

    # Explicit mappings first
    for src, dst in explicit_map.items():
        if src in exclude_set:
            continue
        if dst in dest_set:
            mapping[src] = dst

    # Same-name mappings for remaining columns
    for src in source_columns:
        if src in mapping:
            continue
        if src in exclude_set:
            continue
        if src in dest_set:
            mapping[src] = src

    return mapping


def chunked(iterable: Iterable[Any], size: int) -> Iterable[List[Any]]:
    batch: List[Any] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def select_source_rows(
    conn: psycopg.Connection,
    table: str,
    columns: Sequence[str],
    where: Optional[str],
    batch_size: int,
) -> Iterable[List[Dict[str, Any]]]:
    col_list = ", ".join(f'"{c}"' for c in columns)
    base_sql = f"select {col_list} from {table}"
    if where:
        base_sql += f" where {where}"
    # Server-side cursor to avoid loading all rows into memory
    with conn.cursor(name="src_cursor", row_factory=dict_row) as cur:
        cur.itersize = batch_size
        cur.execute(base_sql)
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            yield rows


def upsert_rows(
    conn: psycopg.Connection,
    dest_table: str,
    mapping: Dict[str, str],
    rows: Sequence[Dict[str, Any]],
    on_conflict: str,
    conflict_target: Sequence[str],
    dry_run: bool,
) -> Tuple[int, int]:
    """
    Insert or upsert rows. Returns (inserted_count, skipped_or_updated_count).
    """
    if not rows:
        return (0, 0)
    src_cols = list(mapping.keys())
    dst_cols = [mapping[s] for s in src_cols]
    dst_cols_sql = ", ".join(f'"{c}"' for c in dst_cols)
    placeholders = ", ".join(["%s"] * len(dst_cols))

    if on_conflict == "skip":
        conflict_sql = f"on conflict ({', '.join(conflict_target)}) do nothing"
        returning = ""
    elif on_conflict == "update":
        # Update all non-conflict columns
        update_assignments = ", ".join(
            f'"{c}" = EXCLUDED."{c}"' for c in dst_cols if c not in conflict_target
        )
        conflict_sql = (
            f"on conflict ({', '.join(conflict_target)}) do update set {update_assignments}"
        )
        returning = ""
    else:
        conflict_sql = ""
        returning = ""

    sql = f"""
        insert into {dest_table} ({dst_cols_sql})
        values ({placeholders})
        {conflict_sql}
        {returning}
    """
    values: List[Tuple[Any, ...]] = []
    for r in rows:
        values.append(tuple(_adapt_value(r.get(s)) for s in src_cols))

    if dry_run:
        return (0, 0)

    with conn.cursor() as cur:
        cur.executemany(sql, values)
    return (len(values), 0)


def _adapt_value(value: Any) -> Any:
    # psycopg3 adapts Decimal, UUID, datetime, etc., automatically.
    # Keep as-is; add minimal normalization when helpful.
    if isinstance(value, Decimal):
        return value  # Do not coerce to float to preserve precision
    return value


def main() -> None:
    args = parse_args()

    if not args.source_dsn:
        raise SystemExit("Missing --source-dsn or SOURCE_DB_DSN")
    if not args.dest_dsn:
        raise SystemExit("Missing --dest-dsn or DEST_DB_DSN")

    dest_table = args.dest_table or args.source_table
    exclude_columns = [c.strip() for c in args.exclude_columns.split(",")] if args.exclude_columns else []
    explicit_map = load_column_map(args.column_map)

    print(f"Source: {args.source_table}")
    print(f"Destination: {dest_table}")
    print(f"Excluding source columns: {exclude_columns}")
    if explicit_map:
        print(f"Using explicit column map for: {list(explicit_map.keys())}")
    print(f"Batch size: {args.batch_size} | On conflict: {args.on_conflict} | Dry-run: {args.dry_run}")
    if args.where:
        print(f"WHERE: {args.where}")

    with psycopg.connect(args.source_dsn) as src_conn, psycopg.connect(args.dest_dsn) as dst_conn:
        src_conn.autocommit = False
        dst_conn.autocommit = False

        src_columns = fetch_columns(src_conn, args.source_table)
        dst_columns = fetch_columns(dst_conn, dest_table)
        pk_columns = fetch_primary_key_columns(dst_conn, dest_table)
        conflict_target = [args.id_column] if args.id_column else (pk_columns or ["id"])

        mapping = build_mapping(
            source_columns=src_columns,
            dest_columns=dst_columns,
            explicit_map=explicit_map,
            excludes=exclude_columns,
        )

        if args.id_column not in mapping and args.id_column in src_columns and args.id_column in dst_columns:
            # Ensure id column is included to preserve UUIDs
            mapping[args.id_column] = args.id_column

        # Log mapping summary
        print("Column mapping (source -> dest):")
        for s, d in mapping.items():
            print(f"  {s} -> {d}")

        missing_in_dest = [s for s, d in mapping.items() if d not in dst_columns]
        if missing_in_dest:
            print(f"Warning: mapped columns not found in destination: {missing_in_dest}", file=sys.stderr)

        migrated = 0
        would_migrate = 0
        for batch in select_source_rows(
            conn=src_conn,
            table=args.source_table,
            columns=list(mapping.keys()),
            where=args.where,
            batch_size=args.batch_size,
        ):
            would_migrate += len(batch)
            inserted, _ = upsert_rows(
                conn=dst_conn,
                dest_table=dest_table,
                mapping=mapping,
                rows=batch,
                on_conflict=args.on_conflict,
                conflict_target=conflict_target,
                dry_run=args.dry_run,
            )
            migrated += inserted
            if not args.dry_run:
                dst_conn.commit()
            print(f"Migrated {migrated} rows...", end="\r", flush=True)

        print()  # newline after progress
        if args.dry_run:
            print(f"Dry-run complete. Would migrate approximately {would_migrate} rows.")
        else:
            print(f"Done. Migrated {migrated} rows.")


if __name__ == "__main__":
    main()


