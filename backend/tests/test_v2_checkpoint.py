def test_checkpoint_scenarios(tmp_path):
    from fake_scenarios import run_checkpoint_scenarios

    run_checkpoint_scenarios(tmp_path)


def test_measurement_validation_and_no_synthetic_claims():
    import pytest
    from latency_bench import summary

    with pytest.raises(ValueError):
        summary([float("nan")])
    with pytest.raises(ValueError):
        summary([-1])
    with pytest.raises(ValueError):
        summary([])
