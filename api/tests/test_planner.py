from app.services.planner import CliPlanner, SimulatedPlanner


def test_simulated_planner_returns_steps():
    steps = SimulatedPlanner().propose("Todo app", "할일 CRUD", context="")
    assert len(steps) >= 1
    assert all(s.label and s.intent and s.acceptance for s in steps)


def test_cli_planner_parses_bare_json_array():
    raw = '[{"label":"a","intent":"i","acceptance":"x"},{"label":"b"}]'
    steps = CliPlanner._parse(raw)
    assert [s.label for s in steps] == ["a", "b"]
    assert steps[1].intent == ""  # missing keys default to empty


def test_cli_planner_parses_fenced_json_and_drops_prose():
    raw = 'Here is the plan:\n```json\n[{"label":"a","intent":"i","acceptance":"x"}]\n```\nDone.'
    steps = CliPlanner._parse(raw)
    assert [s.label for s in steps] == ["a"]
