from app.services.planner import SimulatedPlanner


def test_simulated_planner_returns_steps():
    steps = SimulatedPlanner().propose("Todo app", "할일 CRUD", context="")
    assert len(steps) >= 1
    assert all(s.label and s.intent and s.acceptance for s in steps)
