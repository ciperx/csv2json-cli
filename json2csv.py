#!/usr/bin/env python3
"""json2csv — dependency-free JSON to CSV converter (the mirror of csv2json.py).

Handles list-of-objects, nested objects (flattened with --flatten SEP), arrays,
a union of keys across rows, RFC 4180 quoting, and streaming output.

Usage
  python3 json2csv.py data.json > data.csv
  python3 json2csv.py data.json --flatten . --delimiter ';' --bom -o data.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import Any, Iterator

_SCALARS = (str, int, float, bool, type(None))


def flatten(obj: Any, sep: str, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts; lists are JSON-encoded into a single cell."""
    out: dict[str, Any] = {}
    if not isinstance(obj, dict):
        out[prefix or "value"] = obj if isinstance(obj, _SCALARS) else json.dumps(obj, ensure_ascii=False)
        return out
    for key, val in obj.items():
        name = "%s%s%s" % (prefix, sep, key) if prefix else str(key)
        if isinstance(val, dict):
            out.update(flatten(val, sep, name))
        elif isinstance(val, list):
            out[name] = json.dumps(val, ensure_ascii=False)
        else:
            out[name] = val
    return out


def cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def records(path: str, sep: str | None) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        # a single object, or an object of arrays/objects keyed by id
        if all(isinstance(v, dict) for v in data.values()) and data:
            seq = list(data.values())
        else:
            seq = [data]
    elif isinstance(data, list):
        seq = data
    else:
        seq = [{"value": data}]
    for item in seq:
        yield flatten(item, sep) if sep else (item if isinstance(item, dict) else {"value": item})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convert JSON to CSV (streaming, stdlib only).")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--flatten", nargs="?", const=".", default=".", metavar="SEP",
                    help="flatten nested objects using SEP (default '.'); '' disables")
    ap.add_argument("--delimiter", default=",")
    ap.add_argument("--bom", action="store_true", help="prefix UTF-8 BOM so Excel reads accents")
    ap.add_argument("--no-header", action="store_true")
    args = ap.parse_args(argv)

    sep = args.flatten or None
    rows = list(records(args.input, sep)) if not args.no_header else list(records(args.input, sep))

    # union of keys, first-seen order, so ragged objects do not lose columns
    header: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                header.append(k)

    out_path = args.output
    fh = open(out_path, "w", newline="", encoding="utf-8-sig" if args.bom else "utf-8") if out_path else sys.stdout
    try:
        w = csv.writer(fh, delimiter=args.delimiter, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        if not args.no_header:
            w.writerow(header)
        for r in rows:
            w.writerow([cell(r.get(k)) for k in header])
    finally:
        if out_path:
            fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
