import io
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(tmp_path, payload, *extra):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run([sys.executable, str(ROOT / "json2csv.py"), str(p), *extra],
                          capture_output=True, text=True)


def rows(out, delimiter=","):
    return list(csv.reader(io.StringIO(out), delimiter=delimiter))


def test_basic_list_of_objects(tmp_path):
    r = run(tmp_path, [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    assert r.returncode == 0, r.stderr
    assert rows(r.stdout) == [["a", "b"], ["1", "x"], ["2", "y"]]


def test_union_of_keys_and_missing_cells(tmp_path):
    r = run(tmp_path, [{"a": 1}, {"b": 2}])
    data = rows(r.stdout)
    assert data[0] == ["a", "b"]
    assert data[1] == ["1", ""]
    assert data[2] == ["", "2"]


def test_nested_flatten(tmp_path):
    r = run(tmp_path, [{"user": {"name": "ann", "age": 30}}])
    data = rows(r.stdout)
    assert data[0] == ["user.name", "user.age"]
    assert data[1] == ["ann", "30"]


def test_flatten_disabled_keeps_json_cell(tmp_path):
    r = run(tmp_path, [{"user": {"name": "ann"}}], "--flatten", "")
    data = rows(r.stdout)
    assert data[0] == ["user"]
    assert json.loads(data[1][0]) == {"name": "ann"}


def test_array_cell_is_json(tmp_path):
    r = run(tmp_path, [{"tags": ["a", "b"]}])
    data = rows(r.stdout)
    assert json.loads(data[1][0]) == ["a", "b"]


def test_rfc4180_quoting(tmp_path):
    val = 'has, comma and "quotes"\nand newline'
    r = run(tmp_path, [{"note": val}])
    assert r.returncode == 0, r.stderr
    data = rows(r.stdout)
    assert data[1][0] == val


def test_semicolon_delimiter(tmp_path):
    r = run(tmp_path, [{"a": 1, "b": 2}], "--delimiter", ";")
    assert rows(r.stdout, ";")[0] == ["a", "b"]
    assert ";" in r.stdout.splitlines()[0]


def test_bom_for_excel(tmp_path):
    p = tmp_path / "in.json"
    p.write_text(json.dumps([{"name": "José"}]), encoding="utf-8")
    out = tmp_path / "o.csv"
    r = subprocess.run([sys.executable, str(ROOT / "json2csv.py"), str(p), "--bom", "-o", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "José" in out.read_text(encoding="utf-8-sig")


def test_single_object(tmp_path):
    r = run(tmp_path, {"a": 1, "b": 2})
    assert rows(r.stdout) == [["a", "b"], ["1", "2"]]


def test_object_of_objects(tmp_path):
    r = run(tmp_path, {"one": {"a": 1}, "two": {"a": 2}})
    data = rows(r.stdout)
    assert data[0] == ["a"]
    assert [d[0] for d in data[1:]] == ["1", "2"]


def test_no_header(tmp_path):
    r = run(tmp_path, [{"a": 1}], "--no-header")
    assert rows(r.stdout) == [["1"]]


def test_nulls_and_booleans(tmp_path):
    r = run(tmp_path, [{"a": None, "b": True, "c": False}])
    assert rows(r.stdout)[1] == ["", "true", "false"]


def test_100k_records(tmp_path):
    payload = [{"id": i, "val": i * 2} for i in range(100_000)]
    r = run(tmp_path, payload)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert len(lines) == 100_001
    assert lines[-1] == "99999,199998"
