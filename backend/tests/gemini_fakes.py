"""Hermetic stand-in for ``google.genai.Client`` used by the whole test suite.

The production ``GeminiClient`` builds its SDK client with
``google.genai.Client(...)``; conftest patches that symbol with
``FakeGenai.client_factory`` so every test exercises the real request,
retry, safety and validation code without network access or API quota.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any

DEFAULT_DIAGNOSIS: dict[str, Any] = {
    "image_quality": "good",
    "image_quality_notes": None,
    "plant_identification": {
        "is_plant": True,
        "common_name": "Cucumber",
        "scientific_name": "Cucumis sativus",
        "family": "Cucurbitaceae",
        "genus": "Cucumis",
        "confidence": 0.9,
    },
    "diagnosis": {
        "status": "diseased",
        "primary_condition": "Powdery Mildew",
        "category": "fungal",
        "confidence": 0.82,
        "severity": "moderate",
    },
    "observations": [
        {
            "finding": "White powdery patches on upper leaf surfaces",
            "category": "fungal_sign",
            "certainty": "confirmed",
        }
    ],
    "alternative_diagnoses": [
        {"condition": "Downy Mildew", "confidence": 0.1, "reason": "Underside not visible"}
    ],
    "uncertainties": ["Leaf undersides are not visible."],
    "stress_signal": "none",
    "summary": "Cucumber leaves show white powdery patches consistent with powdery mildew.",
}

DEFAULT_REASONING: dict[str, Any] = {
    "answer": "Your cucumber most likely has powdery mildew; improve airflow and treat it this week.",
    "summary": "Moderate powdery mildew on cucumber.",
    "disease_explanation": "Powdery mildew is a fungal disease that coats leaves in white spores.",
    "possible_causes": ["High humidity with poor airflow"],
    "environmental_analysis": {
        "temperature": "Within the comfortable range.",
        "humidity": "Elevated humidity favours fungal growth.",
        "soil_conditions": "Moisture and pH are acceptable.",
        "light_conditions": "No data",
    },
    "recommendations": ["Remove the worst affected leaves.", "Improve airflow around the plant."],
    "treatment_plan": ["Prune infected leaves", "Apply a potassium bicarbonate spray every 7 days"],
    "prevention": ["Water at the base in the morning"],
    "urgent_actions": [],
    "urgency": "moderate",
    "recovery_assessment": {
        "estimate": "good",
        "confidence": "medium",
        "explanation": "Caught early with treatment available.",
    },
}

DEFAULT_ANNOTATION = '{"label": "Healthy", "confidence": 0.5, "bbox": null, "reasoning": "fake"}'


def make_response(
    text: str | None,
    *,
    finish_reason: str = "STOP",
    block_reason: str | None = None,
    usage: tuple[int, int, int] | None = (120, 80, 200),
) -> SimpleNamespace:
    parts = [SimpleNamespace(text=text, thought=False)] if text is not None else []
    candidates = [] if block_reason else [
        SimpleNamespace(finish_reason=finish_reason, content=SimpleNamespace(parts=parts))
    ]
    return SimpleNamespace(
        candidates=candidates,
        prompt_feedback=SimpleNamespace(block_reason=block_reason) if block_reason else None,
        usage_metadata=(
            SimpleNamespace(prompt_token_count=usage[0], candidates_token_count=usage[1], total_token_count=usage[2])
            if usage
            else None
        ),
    )


class FakeGenai:
    """Configurable fake. ``script`` items are consumed first (responses or exceptions)."""

    def __init__(self) -> None:
        self.diagnosis = copy.deepcopy(DEFAULT_DIAGNOSIS)
        self.reasoning = copy.deepcopy(DEFAULT_REASONING)
        self.annotation_text = DEFAULT_ANNOTATION
        self.script: list[Any] = []
        self.calls: list[dict[str, Any]] = []
        self.clients_built: list[dict[str, Any]] = []
        self.models = SimpleNamespace(generate_content=self.generate_content)

    # google.genai.Client(api_key=..., http_options=...)
    def client_factory(self, *args: Any, **kwargs: Any) -> "FakeGenai":
        self.clients_built.append(kwargs)
        return self

    def generate_content(self, *, model: str, contents: Any, config: Any = None) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        schema = getattr(config, "response_schema", None)
        name = getattr(schema, "__name__", "")
        if name.startswith("GeminiDiagnosis"):
            return make_response(json.dumps(self.diagnosis))
        if name == "GeminiReasoning":
            return make_response(json.dumps(self.reasoning))
        return make_response(self.annotation_text)

    # helpers for assertions
    def calls_for(self, schema_name: str) -> list[dict[str, Any]]:
        return [
            c for c in self.calls
            if getattr(getattr(c["config"], "response_schema", None), "__name__", "") == schema_name
        ]
