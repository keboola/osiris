import pandas as pd

from osiris.core.runner_v0 import RunnerV0


class _StubDriver:
    def __init__(self):
        self.calls = []

    def run(self, step_id, config, inputs, ctx):
        self.calls.append((step_id, config, inputs))
        df = inputs.get("df") if inputs else None
        return {"rows_processed": len(df) if df is not None else 0}


def test_runner_emits_inputs_resolved_for_memory_inputs(tmp_path, monkeypatch):
    events: list[dict] = []

    def capture_event(name: str, **payload):
        events.append({"event": name, **payload})

    monkeypatch.setattr("osiris.core.runner_v0.log_event", capture_event)

    driver = _StubDriver()

    monkeypatch.setattr(
        RunnerV0,
        "_build_driver_registry",
        lambda self: type("Registry", (), {"get": lambda _self, _name: driver})(),
    )

    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("pipeline: {id: test}\\nsteps: []\\n")

    runner = RunnerV0(str(manifest_path), str(tmp_path / "artifacts"))
    runner.results["extract-step"] = {"df": pd.DataFrame({"value": [1, 2, 3]})}

    step = {"id": "process-step", "driver": "dummy.driver", "needs": ["extract-step"]}
    output_dir = tmp_path / "artifacts" / "process-step"
    output_dir.mkdir(parents=True, exist_ok=True)

    success, error = runner._run_with_driver(step, config={}, output_dir=output_dir)

    assert success is True
    assert error is None

    input_events = [event for event in events if event["event"] == "inputs_resolved"]
    assert len(input_events) == 1
    inputs_event = input_events[0]
    assert inputs_event["step_id"] == "process-step"
    assert inputs_event["from_step"] == "extract-step"
    assert inputs_event["key"] == "df"
    assert inputs_event["from_memory"] is True
    assert inputs_event["rows"] == 3

    assert driver.calls, "Driver should have been invoked"
    call_inputs = driver.calls[0][2]
    assert "df" in call_inputs
    assert list(call_inputs["df"]["value"]) == [1, 2, 3]
