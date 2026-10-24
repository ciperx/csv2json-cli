import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import csv2json as C  # noqa: E402


def write(tmp_path, name, data, encoding="utf-8"):
    p = tmp_path / name
    p.write_text(data, encoding=encoding)
    return p


def run(path, *extra):
    return subprocess.run([sys.executable, str(ROOT / "csv2json.py"), str(path), *extra],
                          capture_output=True, text=True)


def test_infer_types():
    assert C.infer("42") == 42
    assert C.infer("-7") == -7
    assert C.infer("3.5") == 3.5
    assert C.infer("1e3") == 1000.0
    assert C.infer("true") is True
    assert C.infer("No") is False
    assert C.infer("") is None
    assert C.infer("null") is None
    assert C.infer("2026-10-24") == "2026-10-24"
    assert C.infer("hello") == "hello"
    assert C.infer("0042") == 42  # documented: leading zeros become ints


def test_delimiter_detection():
    assert C.detect_delimiter("a,b\n1,2\n3,4\n") == ","
    assert C.detect_delimiter("a;b\n1;2\n3;4\n") == ";"
    assert C.detect_delimiter("a\tb\n1\t2\n") == "\t"
    assert C.detect_delimiter("single\nlines\n") == ","  # fallback


def test_basic_conversion(tmp_path):
    p = write(tmp_path, "a.csv", "name,qty,price\nwidget,3,9.5\n")
    r = run(p)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [{"name": "widget", "qty": 3, "price": 9.5}]


def test_quoted_field_with_newline_and_quotes(tmp_path):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "note"])
    w.writerow([1, 'line1\nline2, with "quotes"'])
    p = write(tmp_path, "q.csv", buf.getvalue())
    r = run(p)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data[0]["note"] == 'line1\nline2, with "quotes"'


def test_bom_is_stripped(tmp_path):
    p = tmp_path / "bom.csv"
    p.write_bytes("\ufeffname,age\nanna,30\n".encode("utf-8"))
    r = run(p)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert list(data[0].keys()) == ["name", "age"]
    assert data[0] == {"name": "anna", "age": 30}


def test_latin1_fallback(tmp_path):
    p = tmp_path / "l1.csv"
    p.write_bytes("name\nJosé\n".encode("latin-1"))
    r = run(p)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)[0]["name"] == "José"


def test_ragged_rows_warn_and_pad(tmp_path):
    p = write(tmp_path, "r.csv", "a,b,c\n1,2,3\n4,5\n")
    r = run(p)
    assert r.returncode == 0
    assert "warning:" in r.stderr
    rows = json.loads(r.stdout)
    assert rows[1] == {"a": 4, "b": 5, "c": None}


def test_ragged_rows_strict_fails(tmp_path):
    p = write(tmp_path, "r.csv", "a,b\n1\n")
    r = run(p, "--strict")
    assert r.returncode != 0
    assert "expected 2" in (r.stderr + r.stdout)


def test_empty_file(tmp_path):
    p = write(tmp_path, "e.csv", "")
    r = run(p)
    assert r.returncode == 0
    assert json.loads(r.stdout) == []


def test_headerless_with_columns(tmp_path):
    p = write(tmp_path, "h.csv", "1,2\n3,4\n")
    r = run(p, "--no-header", "--columns", "x,y")
    data = json.loads(r.stdout)
    assert data == [{"x": 1, "y": 2}, {"x": 3, "y": 4}]


def test_headerless_without_columns_autonames(tmp_path):
    p = write(tmp_path, "h2.csv", "1,2\n")
    r = run(p, "--no-header")
    assert json.loads(r.stdout) == [{"column_1": 1, "column_2": 2}]


def test_no_infer_keeps_strings(tmp_path):
    p = write(tmp_path, "n.csv", "a,b\n1,true\n")
    r = run(p, "--no-infer")
    assert json.loads(r.stdout) == [{"a": "1", "b": "true"}]


def test_nest(tmp_path):
    p = write(tmp_path, "n2.csv", "user.name,user.age\nann,30\n")
    r = run(p, "--nest", ".")
    assert json.loads(r.stdout) == [{"user": {"name": "ann", "age": 30}}]


def test_pretty_and_output_file(tmp_path):
    p = write(tmp_path, "p.csv", "a\n1\n")
    out = tmp_path / "p.json"
    r = run(p, "--pretty", "-o", str(out))
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text()) == [{"a": 1}]
    assert "\n  " in out.read_text()


def test_semicolon_detected(tmp_path):
    p = write(tmp_path, "s.csv", "a;b\n1;2\n")
    assert json.loads(run(p).stdout) == [{"a": 1, "b": 2}]


def test_100k_rows_streams(tmp_path):
    p = tmp_path / "big.csv"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("id,val\n")
        for i in range(100_000):
            fh.write("%d,%d\n" % (i, i * 2))
    r = run(p, "--pretty")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert len(data) == 100_000
    assert data[-1] == {"id": 99_999, "val": 199_998}
