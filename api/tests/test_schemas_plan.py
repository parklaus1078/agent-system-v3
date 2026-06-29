from app.schemas_plan import PlanProposal, ReviewAction


def test_plan_and_review_validate():
    p = PlanProposal(ticket_id="t1", steps=[{"label": "spec", "intent": "i", "acceptance": "a"}])
    assert p.steps[0].label == "spec"
    assert ReviewAction(kind="changes", comment="fix x").comment == "fix x"
