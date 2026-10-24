# csv2json

Dependency-free CSV → JSON converter. One file, stdlib only, streaming.

```bash
python3 csv2json.py data.csv > data.json
python3 csv2json.py data.csv --delimiter ';' --nest . --pretty -o data.json
python3 csv2json.py data.csv --no-header --columns id,name --strict
```

## What it handles

| Feature | Flag | Notes |
|---|---|---|
| Delimiter auto-detect | `--delimiter` to force | comma, semicolon, tab, pipe — chosen by field-count consistency over the first 20 lines |
| Encoding | `--encoding` to force | tries `utf-8-sig`, `utf-8`, `latin-1`; BOM is stripped |
| Type inference | `--no-infer` to disable | int, float, bool, ISO date, null |
| Headerless input | `--no-header`, `--columns a,b` | auto-names `column_1..n` when no names are given |
| Streaming | — | rows are written one at a time; only `--pretty` buffers |
| Ragged rows | `--strict` to fail | default pads/truncates and warns on stderr |
| Nested objects | `--nest SEP` | `user.name,user.age` → `{"user":{"name":…,"age":…}}` |

## Tests

```bash
python3 -m pytest -q
# 16 passed
```

Cases covered: quoted fields with embedded newlines and quotes, UTF-8 BOM, Latin-1 input,
ragged rows (warn and strict), empty file, headerless with and without column names,
type inference on/off, nesting, `--pretty` with `-o`, semicolon detection, and a 100 000-row run.

## Deliberate behaviour worth knowing

- `0042` becomes the integer `42`. Use `--no-infer` when leading zeros matter (ZIP codes, phone numbers).
- Empty string, `null`, `none`, `na`, `n/a` and `-` all become JSON `null`.
- A single-column file falls back to the comma delimiter, because field-count consistency cannot distinguish delimiters on one field.
- `--strict` raises on the first ragged row and exits non-zero; the message names the line and both counts.

MIT.
