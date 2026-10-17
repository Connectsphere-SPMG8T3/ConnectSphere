"""Summarise a mutmut run as a per-file table (docs/MUTATION_TESTING.md).

Run from backend/ after `mutmut run`:

    mutmut results --all true | python scripts/mutation_report.py              # markdown table
    mutmut results --all true | python scripts/mutation_report.py --survivors  # one survivor per line

Mutants a scoped run did not check ("not checked") are left out, so the table
covers only the module that was run. A timeout counts as killed: the mutant
made the code hang and the run noticed.
"""

import argparse
import sys

_KILLED = {"killed", "timeout"}
_TRACKED = ("killed", "survived", "no tests")


def _parse(results: str) -> list[tuple[str, str]]:
    rows = []
    for line in results.splitlines():
        name, sep, status = line.strip().rpartition(": ")
        if sep and name:
            rows.append((name, status.strip()))
    return rows


def _file_of(mutant: str) -> str:
    """`app.modules.venues.service.x_get_venue__mutmut_1` → `venues/service.py`."""
    parts = mutant.split(".")
    module = []
    for part in parts[1:]:
        if part.startswith("x"):
            break
        module.append(part)
    if module and module[0] == "modules":
        module = module[1:]
    return "/".join(module) + ".py"


def count_by_file(results: str) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for mutant, status in _parse(results):
        if status == "not checked":
            continue
        row = counts.setdefault(_file_of(mutant), {"killed": 0, "survived": 0, "no tests": 0, "other": 0})
        if status in _KILLED:
            row["killed"] += 1
        elif status in _TRACKED:
            row[status] += 1
        else:
            row["other"] += 1
    return counts


def _percent(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "–"


def _row(label: str, c: dict[str, int], bold: bool = False) -> str:
    total = sum(c.values())
    cells = [
        str(c["killed"]),
        str(c["survived"]),
        str(c["no tests"]),
        str(c["other"]),
        _percent(c["killed"], total),
        _percent(c["killed"], c["killed"] + c["survived"]),
    ]
    if bold:
        cells = [f"**{cell}**" for cell in cells]
    return f"| {label} | " + " | ".join(cells) + " |"


def markdown_table(counts: dict[str, dict[str, int]]) -> str:
    if not counts:
        return "No mutants were checked."
    lines = [
        "| File | Killed | Survived | No test | Other | Score | Reached |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    total = {"killed": 0, "survived": 0, "no tests": 0, "other": 0}
    for path in sorted(counts):
        lines.append(_row(f"`{path}`", counts[path]))
        for key, value in counts[path].items():
            total[key] += value
    lines.append(_row("**Total**", total, bold=True))
    return "\n".join(lines)


def survivors(results: str) -> list[str]:
    return [mutant for mutant, status in _parse(results) if status == "survived"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--survivors", action="store_true", help="print surviving mutant names instead of the table")
    args = parser.parse_args()
    results = sys.stdin.read()
    print("\n".join(survivors(results)) if args.survivors else markdown_table(count_by_file(results)))


if __name__ == "__main__":
    main()
