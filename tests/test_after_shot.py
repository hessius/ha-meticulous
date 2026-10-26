"""Regression coverage for live and historical after-shot measurements."""

import json
from pathlib import Path

import pytest

from custom_components.meticulous_espresso.after_shot import summarise
from custom_components.meticulous_espresso.history_import import _shot_summary


def row(status="retracting", current=1.0, speed=-10.0, power=-100.0):
    """Match the firmware's Shot.addShotData / Shot.addSensorData format."""
    return {
        "status": status,
        "shot": {"pressure": 0.0},
        "sensors": {
            "motor_position": 45.0,
            "motor_speed": speed,
            "motor_power": power,
            "motor_current": current,
        },
    }


def history(*rows):
    return {"data": list(rows)}


def test_minimum_home_assistant_version():
    config = Path(__file__).resolve().parents[1] / "hacs.json"
    assert json.loads(config.read_text())["homeassistant"] == "2025.4.0"


def test_history_uses_only_post_shot_retraction():
    shot = history(
        row("click to start"),
        *[row(current=8.0) for _ in range(7)],
        row("Bloom", current=9.0),
        *[row(current=1.0) for _ in range(5)],
        row("idle"),
    )
    assert _shot_summary(shot) == (1.0, 10.0)


@pytest.mark.parametrize(
    "preceding", [None, "", "unknown", "idle", "click_to_start", "home", "finished"]
)
def test_history_requires_known_post_shot_context(preceding):
    rows = [] if preceding is None else [row(preceding)]
    rows.extend(row() for _ in range(5))
    assert _shot_summary(history(*rows)) is None


def test_history_does_not_classify_a_profile_stage_as_retraction():
    assert _shot_summary(history(*[row("Bloom") for _ in range(5)])) is None


@pytest.mark.parametrize("field", ["motor_position", "motor_speed", "motor_power", "motor_current"])
def test_history_requires_complete_motor_samples(field):
    rows = [row("Extraction")]
    for _ in range(5):
        sample = row()
        del sample["sensors"][field]
        rows.append(sample)
    assert _shot_summary(history(*rows)) is None


@pytest.mark.parametrize("pressure", [None, "invalid", float("nan"), float("inf")])
def test_history_rejects_invalid_pressure(pressure):
    rows = [row("Extraction")]
    for _ in range(5):
        sample = row()
        sample["shot"]["pressure"] = pressure
        rows.append(sample)
    assert _shot_summary(history(*rows)) is None


def test_history_rejects_missing_pressure():
    rows = [row("Extraction")]
    for _ in range(5):
        sample = row()
        sample["shot"] = {}
        rows.append(sample)
    assert _shot_summary(history(*rows)) is None


def test_history_keeps_transition_context_without_motor_data():
    rows = [{"status": "Extraction"}]
    rows.extend(row() for _ in range(5))
    assert _shot_summary(history(*rows)) == (1.0, 10.0)


def test_history_does_not_reuse_context_after_missing_status():
    rows = [row("Extraction"), row(None)]
    rows.extend(row() for _ in range(5))
    assert _shot_summary(history(*rows)) is None


@pytest.mark.parametrize("speed,power", [(10.0, 100.0), (-10.0, 100.0), (10.0, -100.0)])
def test_summary_rejects_wrong_direction(speed, power):
    assert summarise([(45.0, speed, power, 1.0, 0.0)] * 5) is None


@pytest.mark.parametrize("index", range(5))
def test_summary_rejects_non_finite_values(index):
    samples = []
    for value in [float("nan"), float("inf"), float("-inf")]:
        sample = [45.0, -10.0, -100.0, 1.0, 0.0]
        sample[index] = value
        samples.extend([tuple(sample)] * 5)
    assert summarise(samples) is None


def test_summary_preserves_median_and_thresholds():
    samples = [(45.0, -10.0, -100.0, current, 0.0) for current in [1, 1.1, 1.2, 1.3, 9]]
    assert summarise(samples) == (1.2, 10.0)
    assert summarise(samples[:4]) is None


@pytest.mark.parametrize("position", [35.0, 55.0])
def test_summary_includes_exact_retract_thresholds(position):
    assert summarise([(position, -8.0, -99.0, -1.0, 0.099)] * 5) == (1.0, 8.0)


@pytest.mark.parametrize(
    "sample",
    [
        (34.99, -10.0, -100.0, 1.0, 0.0),
        (55.01, -10.0, -100.0, 1.0, 0.0),
        (45.0, -7.99, -100.0, 1.0, 0.0),
        (45.0, -10.0, -98.99, 1.0, 0.0),
        (45.0, -10.0, -100.0, 1.0, 0.1),
    ],
)
def test_summary_excludes_samples_outside_thresholds(sample):
    assert summarise([sample] * 5) is None
