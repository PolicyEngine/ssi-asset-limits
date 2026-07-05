from ssi_asset_limits import pipeline


def test_build_simulations_uses_policyengine_py_managed_default(monkeypatch):
    calls = []

    def fake_managed_microsimulation(**kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(
        pipeline,
        "_managed_microsimulation_factory",
        lambda: fake_managed_microsimulation,
    )
    monkeypatch.setattr(
        pipeline,
        "create_asset_limit_reform",
        lambda **kwargs: {"reform_kwargs": kwargs},
    )

    pipeline.build_simulations(
        individual_limit=10_000,
        couple_limit=20_000,
        reform_start_year=2026,
    )

    assert calls[0] == {"dataset": None, "allow_unmanaged": False}
    assert calls[1] == {
        "dataset": None,
        "allow_unmanaged": False,
        "reform": {
            "reform_kwargs": {
                "individual_limit": 10_000,
                "couple_limit": 20_000,
                "start_year": 2026,
            }
        },
    }


def test_build_simulations_marks_dataset_override_unmanaged(monkeypatch):
    calls = []

    def fake_managed_microsimulation(**kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(
        pipeline,
        "_managed_microsimulation_factory",
        lambda: fake_managed_microsimulation,
    )
    monkeypatch.setattr(
        pipeline,
        "create_asset_limit_reform",
        lambda **kwargs: {"reform_kwargs": kwargs},
    )

    pipeline.build_simulations(dataset="/tmp/populace_us_2024.h5")

    assert calls[0]["dataset"] == "/tmp/populace_us_2024.h5"
    assert calls[0]["allow_unmanaged"] is True
    assert calls[1]["dataset"] == "/tmp/populace_us_2024.h5"
    assert calls[1]["allow_unmanaged"] is True
