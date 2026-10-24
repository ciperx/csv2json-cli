#!/usr/bin/env python3
"""csv2json — dependency-free CSV to JSON converter.

Features
  1. delimiter auto-detection (comma, semicolon, tab, pipe) with --delimiter override
  2. encoding detection (utf-8-sig, utf-8, latin-1) with --encoding override
  3. per-column type inference (int, float, bool, ISO date, null) with --no-infer
  4. headerless input (--no-header, --columns a,b,c)
  5. streaming output: reads row by row, never holds the file in memory
  6. --strict fails on ragged rows; default pads/truncates with a warning to stderr
  7. --nest creates nested objects from a column name separator (default ".")

Usage
  python3 csv2json.py data.csv > data.json
  python3 csv2json.py data.csv --delimiter ';' --nest . --pretty
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import re
import sys
from typing import Any, Iterable, Iterator

DELIMS = [",", ";", "\t", "|"]
ENCODINGS = ["utf-8-sig", "utf-8", "latin-1"]
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}
_NULL = {"", "null", "none", "na", "n/a", "-"}


def detect_encoding(path: str) -> str:
    """Return the first encoding that decodes the first 64 KiB without error."""
    raw = open(path, "rb").read(65536)
    for enc in ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def detect_delimiter(sample: str) -> str:
    """Pick the delimiter with the most consistent field count across lines."""
    lines = [ln for ln in sample.splitlines() if ln.strip()][:20]
    if not lines:
        return ","
    best, best_score = ",", -1.0
    for d in DELIMS:
        counts = [len(next(csv.reader([ln], delimiter=d))) for ln in lines]
        if not counts:
            continue
        mode = max(set(counts), key=counts.count)
        if mode <= 1:
            continue
        score = counts.count(mode) / len(counts)
        if score > best_score:
            best, best_score = d, score
    return best


def infer(value: str) -> Any:
    """Convert one CSV field to the most specific JSON type it can hold."""
    v = value.strip()
    low = v.lower()
    if low in _NULL:
        return None
    if low in _TRUE and len(v) <= 4:
        return True
    if low in _FALSE and len(v) <= 5:
        return False
    if _INT_RE.match(v):
        try:
            return int(v)
        except ValueError:
            pass
    if _FLOAT_RE.match(v) and ("." in v or "e" in low):
        try:
            return float(v)
        except ValueError:
            pass
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        try:
            _dt.date.fromisoformat(v)
            return v
        except ValueError:
            pass
    return v


def nest(row: dict[str, Any], sep: str) -> dict[str, Any]:
    """Turn {"a.b": 1} into {"a": {"b": 1}}."""
    if not sep or not any(sep in k for k in row):
        return row
    out: dict[str, Any] = {}
    for key, val in row.items():
        parts = key.split(sep)
        cur = out
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
            if not isinstance(cur, dict):
                cur = {}
        cur[parts[-1]] = val
    return out


def rows(path: str, encoding: str, delimiter: str, header: bool,
         columns: list[str] | None, strict: bool) -> Iterator[dict[str, Any]]:
    with open(path, newline="", encoding=encoding) as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        names: list[str] | None = None
        if header:
            try:
                names = next(reader)
            except StopIteration:
                return
            names = [n.strip() for n in names]
        elif columns:
            names = columns
        for lineno, rec in enumerate(reader, start=2 if header else 1):
            if not rec or all(c.strip() == "" for c in rec):
                continue
            if names is None:
                names = ["column_%d" % i for i in range(1, len(rec) + 1)]
            if len(rec) != len(names):
                msg = "line %d: %d fields, expected %d" % (lineno, len(rec), len(names))
                if strict:
                    raise ValueError(msg)
                print("warning: " + msg, file=sys.stderr)
                rec = (rec + [""] * len(names))[:len(names)]
            yield dict(zip(names, rec))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convert CSV to JSON (streaming, stdlib only).")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--delimiter", help="force a delimiter, e.g. ';'")
    ap.add_argument("--encoding", help="force an encoding, e.g. latin-1")
    ap.add_argument("--no-header", action="store_true")
    ap.add_argument("--columns", help="comma-separated names for headerless input")
    ap.add_argument("--no-infer", action="store_true")
    ap.add_argument("--nest", nargs="?", const=".", default=None, metavar="SEP")
    ap.add_argument("--pretty", action="store_true", help="indent JSON (buffers everything)")
    ap.add_argument("--strict", action="store_true", help="fail on ragged rows")
    args = ap.parse_args(argv)

    enc = args.encoding or detect_encoding(args.input)
    if args.delimiter:
        delim = args.delimiter
    else:
        with open(args.input, encoding=enc, errors="replace") as fh:
            delim = detect_delimiter(fh.read(65536))
    cols = [c.strip() for c in args.columns.split(",")] if args.columns else None

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        if args.pretty:
            data = []
            for r in rows(args.input, enc, delim, not args.no_header, cols, args.strict):
                if not args.no_infer:
                    r = {k: infer(v) for k, v in r.items()}
                data.append(nest(r, args.nest) if args.nest else r)
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
        else:
            out.write("[")
            first = True
            for r in rows(args.input, enc, delim, not args.no_header, cols, args.strict):
                if not args.no_infer:
                    r = {k: infer(v) for k, v in r.items()}
                if args.nest:
                    r = nest(r, args.nest)
                if not first:
                    out.write(",")
                out.write(json.dumps(r, ensure_ascii=False))
                first = False
            out.write("]\n")
    finally:
        if args.output:
            out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
