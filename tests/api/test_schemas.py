import json
from pathlib import Path

from trackhealth.api.schemas import MetricsResponse, ReadingsResponse, SeriesResponse, StateResponse
from trackhealth.metrics.registry import REGISTRY

CONTRACT_FIXTURES = Path(__file__).parents[1] / "fixtures" / "contract"


def load_fixture(name: str) -> dict:
    return json.loads((CONTRACT_FIXTURES / name).read_text())


def test_state_fixture_validates_against_frozen_contract() -> None:
    response = StateResponse.model_validate(load_fixture("state.json"))

    assert set(response.metrics) == set(REGISTRY)
    for key, metric in response.metrics.items():
        spec = REGISTRY[key]
        assert metric.label == spec.label
        assert metric.unit == spec.unit
        assert metric.has_readings == spec.has_readings
        assert isinstance(metric.value, spec.value_type)


def test_series_fixture_validates_against_frozen_contract() -> None:
    response = SeriesResponse.model_validate(load_fixture("series.json"))

    assert response.metric == "steps"
    assert response.range == "1y"
    assert response.points == sorted(response.points, key=lambda point: point.at)


def test_readings_fixture_validates_against_frozen_contract() -> None:
    response = ReadingsResponse.model_validate(load_fixture("readings.json"))

    assert response.metric == "hrv"
    assert response.on.isoformat() == "2026-06-30"
    assert response.readings


def test_metrics_fixture_validates_against_registry() -> None:
    response = MetricsResponse.model_validate(load_fixture("metrics.json"))

    assert [metric.key for metric in response.metrics] == list(REGISTRY)
    assert [
        (metric.key, metric.label, metric.unit, metric.has_readings, metric.agg)
        for metric in response.metrics
    ] == [
        (spec.key, spec.label, spec.unit, spec.has_readings, spec.agg)
        for spec in REGISTRY.values()
    ]
