def test_operational_integration_table(tmp_path):
    from operational_scenarios import run_operational_scenarios

    run_operational_scenarios(tmp_path, report=lambda line: None)
