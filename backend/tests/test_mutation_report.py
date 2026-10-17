"""scripts/mutation_report.py turns `mutmut results --all true` into the
per-file table the manual "Mutation testing" workflow shows on its summary
page (docs/MUTATION_TESTING.md)."""

from scripts import mutation_report

RESULTS = """\
    app.modules.venues.service.x_get_venue__mutmut_1: killed
    app.modules.venues.service.x_get_venue__mutmut_2: survived
    app.modules.venues.service.x_update_venue__mutmut_7: killed
    app.modules.venues.repository.x_list_venues__mutmut_1: no tests
    app.modules.venues.repository.x_list_venues__mutmut_2: timeout
    app.core.security.x_decode_access_token__mutmut_1: not checked
    app.core.security.x_decode_access_token__mutmut_2: segfault
"""


def test_counts_are_grouped_by_file_and_unchecked_mutants_are_left_out():
    counts = mutation_report.count_by_file(RESULTS)

    assert counts == {
        "venues/service.py": {"killed": 2, "survived": 1, "no tests": 0, "other": 0},
        "venues/repository.py": {"killed": 1, "survived": 0, "no tests": 1, "other": 0},
        "core/security.py": {"killed": 0, "survived": 0, "no tests": 0, "other": 1},
    }


def test_a_timeout_counts_as_killed():
    # The mutant made the code hang and the run noticed, as StrykerJS counts it.
    counts = mutation_report.count_by_file("    app.modules.events.service.x_f__mutmut_1: timeout\n")

    assert counts["events/service.py"]["killed"] == 1


def test_the_table_has_a_score_per_file_and_a_total():
    table = mutation_report.markdown_table(mutation_report.count_by_file(RESULTS))

    assert table.splitlines() == [
        "| File | Killed | Survived | No test | Other | Score | Reached |",
        "|---|---:|---:|---:|---:|---:|---:|",
        "| `core/security.py` | 0 | 0 | 0 | 1 | 0% | – |",
        "| `venues/repository.py` | 1 | 0 | 1 | 0 | 50% | 100% |",
        "| `venues/service.py` | 2 | 1 | 0 | 0 | 67% | 67% |",
        "| **Total** | **3** | **1** | **1** | **1** | **50%** | **75%** |",
    ]


def test_survivors_are_listed_by_name():
    assert mutation_report.survivors(RESULTS) == ["app.modules.venues.service.x_get_venue__mutmut_2"]


def test_nothing_checked_says_so():
    assert mutation_report.markdown_table({}) == "No mutants were checked."
