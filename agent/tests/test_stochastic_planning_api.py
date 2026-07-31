from pydantic import ValidationError
import pytest

from app.api.agentos_core import WorkflowStartRequest, _normalize_acg_start_request


def test_workflow_start_accepts_camel_case_stochastic_planning_fields():
    request = WorkflowStartRequest.model_validate(
        {
            "title": "Varied ACG",
            "input": {"source": "acg", "userIntent": "prepare a plan"},
            "planningDiversity": "exploratory",
            "planningSeed": 284731,
        }
    )

    normalized = _normalize_acg_start_request(request)

    assert normalized.planning_diversity == "exploratory"
    assert normalized.planning_seed == 284731
    assert normalized.input["planningDiversity"] == "exploratory"
    assert normalized.input["planningSeed"] == 284731


@pytest.mark.parametrize(
    "payload",
    [
        {"planningDiversity": "arbitrary"},
        {"planningSeed": -1},
        {"planningSeed": 2**53},
    ],
)
def test_workflow_start_rejects_invalid_stochastic_planning_fields(payload):
    with pytest.raises(ValidationError):
        WorkflowStartRequest.model_validate({"title": "Invalid", **payload})


def test_omitted_stochastic_fields_keep_legacy_request_input_unchanged():
    request = WorkflowStartRequest(title="Stable", input={"source": "api"})

    normalized = _normalize_acg_start_request(request)

    assert normalized.planning_diversity is None
    assert normalized.planning_seed is None
    assert "planningDiversity" not in normalized.input
    assert "planningSeed" not in normalized.input
