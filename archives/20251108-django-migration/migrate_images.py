#!/usr/bin/env python3
import argparse
import os
import sys
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import psycopg
from psycopg.rows import dict_row


@dataclass
class ImageRow:
    id: int
    artwork_id: str
    image_path: str
    is_main_image: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate images: download from existing deployment via curl and upload to production image-create endpoint via curl."
    )
    parser.add_argument(
        "--source-dsn",
        default=os.environ.get("SOURCE_DB_DSN"),
        help="Source Postgres DSN (local Django DB). Can also be set via SOURCE_DB_DSN.",
    )
    parser.add_argument(
        "--source-table",
        default=os.environ.get("SOURCE_IMAGE_TABLE", "artwork_image"),
        help="Source image table name. Default: artwork_image",
    )
    parser.add_argument(
        "--where",
        default=os.environ.get("WHERE"),
        help="Optional SQL WHERE clause (without WHERE) to limit images (e.g. \"id >= 1000\").",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("LIMIT", "0")),
        help="Optional LIMIT on number of images to process. 0 means no limit.",
    )
    parser.add_argument(
        "--fetch-prefix",
        default=os.environ.get("FETCH_PREFIX"),
        help="Base URL prefix to fetch the raw image bytes, concatenated with the 'image' field from the source row. Example: https://old.example.com/media/",
    )
    parser.add_argument(
        "--save-dir",
        default=os.environ.get("SAVE_DIR", "images"),
        help="Local subdirectory (relative to scripts/) to store downloaded images. Default: images",
    )
    parser.add_argument(
        "--upload-prefix",
        default=os.environ.get("UPLOAD_PREFIX"),
        help="Base URL prefix of the backend (e.g., https://api.example.com). Final URL becomes <prefix>/artworks/{artwork_id}/images",
    )
    parser.add_argument(
        "--upload-url",
        default=os.environ.get("UPLOAD_URL"),
        help="Optional explicit URL or template. If it contains '{artwork_id}', it will be formatted per row. Otherwise prefer --upload-prefix.",
    )
    parser.add_argument(
        "--cookie",
        default=os.environ.get("COOKIE"),
        help='Cookie header value containing access token, e.g. "access_token=...". Will be sent as: -H "Cookie: <value>".',
    )
    parser.add_argument(
        "--upload-field-file",
        default=os.environ.get("UPLOAD_FIELD_FILE", "image"),
        help="Form field name for file upload. Default: image",
    )
    parser.add_argument(
        "--upload-field-is-main",
        default=os.environ.get("UPLOAD_FIELD_IS_MAIN", "is_main_image"),
        help="Form field name for main-image flag. Default: is_main_image",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If set, print curl commands but do not execute them.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="If set, skip downloading and assume files already exist in --save-dir with same relative paths.",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete downloaded files after successful upload.",
    )
    return parser.parse_args()


def ensure_prereqs(args: argparse.Namespace) -> None:
    if not args.source_dsn:
        raise SystemExit("Missing --source-dsn or SOURCE_DB_DSN")
    if not args.fetch_prefix:
        raise SystemExit("Missing --fetch-prefix or FETCH_PREFIX (needed to download images).")
    if not args.upload_prefix and not (args.upload_url and "{artwork_id}" in args.upload_url):
        raise SystemExit("Provide --upload-prefix, or --upload-url containing '{artwork_id}'.")
    if not args.cookie:
        raise SystemExit("Missing --cookie or COOKIE (needed for authenticated upload).")


def join_url(prefix: str, path: str) -> str:
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def abs_scripts_path(*parts: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, *parts)


def query_images(
    conn: psycopg.Connection, table: str, where: Optional[str], limit: int
) -> Iterable[ImageRow]:
    sql = f"""
        select id, artwork_id, image as image_path, is_main_image
        from {table}
    """
    if where:
        sql += f" where {where}"
    sql += " order by id"
    if limit and limit > 0:
        sql += f" limit {int(limit)}"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        for r in cur:
            yield ImageRow(
                id=r["id"],
                artwork_id=str(r["artwork_id"]),
                image_path=str(r["image_path"]),
                is_main_image=bool(r["is_main_image"]),
            )


def run_curl(args_list: List[str], dry_run: bool) -> Tuple[int, str, str]:
    if dry_run:
        print("$ " + " ".join(shlex.quote(a) for a in args_list))
        return (0, "", "")
    proc = subprocess.run(args_list, capture_output=True, text=True)
    return (proc.returncode, proc.stdout, proc.stderr)


def download_image(fetch_url: str, dest_path: str, dry_run: bool) -> None:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    cmd = ["curl", "-sS", "-fL", fetch_url, "-o", dest_path]
    code, out, err = run_curl(cmd, dry_run)
    if not dry_run and code != 0:
        raise RuntimeError(f"Download failed ({code}) for {fetch_url}: {err.strip() or out.strip()}")


def upload_image(
    upload_url: str,
    cookie: str,
    file_field: str,
    file_path: str,
    is_main_field: str,
    is_main: bool,
    dry_run: bool,
) -> None:
    is_main_val = "true" if is_main else "false"
    cmd = [
        "curl",
        "-sS",
        "-fL",
        "-X",
        "POST",
        "-H",
        f"Cookie: {cookie}",
        "-F",
        f"{file_field}=@{file_path}",
        "-F",
        f"{is_main_field}={is_main_val}",
        upload_url,
    ]
    code, out, err = run_curl(cmd, dry_run)
    if not dry_run and code != 0:
        raise RuntimeError(f"Upload failed ({code}) for {os.path.basename(file_path)}: {err.strip() or out.strip()}")


def resolve_upload_url(args: argparse.Namespace, artwork_id: str) -> str:
    if args.upload_prefix:
        return join_url(args.upload_prefix, f"artworks/{artwork_id}/images")
    if args.upload_url and "{artwork_id}" in args.upload_url:
        return args.upload_url.replace("{artwork_id}", artwork_id)
    # As a last resort, if a plain upload_url was provided, use it (may be incorrect)
    if args.upload_url:
        return args.upload_url
    raise RuntimeError("Unable to resolve upload URL: provide --upload-prefix or --upload-url with '{artwork_id}'.")


def main() -> None:
    args = parse_args()
    ensure_prereqs(args)

    save_root = abs_scripts_path(args.save_dir)
    print(f"Download dir: {save_root}")
    print(f"Fetch prefix: {args.fetch_prefix}")
    if args.upload_prefix:
        print(f"Upload prefix: {args.upload_prefix}")
    else:
        print(f"Upload URL template: {args.upload_url}")

    total = 0
    downloaded = 0
    uploaded = 0
    skipped_download = 0

    with psycopg.connect(args.source_dsn) as src_conn:
        for row in query_images(src_conn, args.source_table, args.where, args.limit):
            total += 1
            fetch_url = join_url(args.fetch_prefix, row.image_path)
            local_path = os.path.join(save_root, row.image_path)

            try:
                if args.skip_download and os.path.exists(local_path):
                    skipped_download += 1
                else:
                    download_image(fetch_url, local_path, args.dry_run)
                    downloaded += 1

                dest_url = resolve_upload_url(args, row.artwork_id)
                upload_image(
                    upload_url=dest_url,
                    cookie=args.cookie,
                    file_field=args.upload_field_file,
                    file_path=local_path,
                    is_main_field=args.upload_field_is_main,
                    is_main=row.is_main_image,
                    dry_run=args.dry_run,
                )
                uploaded += 1

                if args.cleanup and not args.dry_run and os.path.exists(local_path):
                    # Best-effort cleanup; ignore errors
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass

            except Exception as exc:
                print(f"\nError processing image id={row.id} path='{row.image_path}': {exc}", file=sys.stderr)

            if total % 10 == 0:
                print(
                    f"\rProcessed {total} | downloaded {downloaded} | skipped {skipped_download} | uploaded {uploaded}",
                    end="",
                    flush=True,
                )

    print()
    if args.dry_run:
        print(
            f"Dry-run complete. Would process {total} images "
            f"(download {total if not args.skip_download else total - skipped_download}, upload {total})."
        )
    else:
        print(f"Done. Processed {total} images (downloaded {downloaded}, skipped {skipped_download}, uploaded {uploaded}).")


if __name__ == "__main__":
    main()


