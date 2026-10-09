import json

import pytest

from bible_reader.cli import load_config, main


def test_init_refuses_overwrite_and_inspect_is_offline(source_state, tmp_path, capsys):
    config = tmp_path / "project.json"
    assert main(["init", "--project", str(config)]) == 0
    original = config.read_bytes()
    with pytest.raises(SystemExit) as error:
        main(["init", "--project", str(config)])
    assert error.value.code == 1
    assert config.read_bytes() == original
    report = tmp_path / "report.json"
    assert (
        main(["--state", str(source_state), "inspect", "--project", str(config), "--report", str(report)])
        == 0
    )
    assert json.loads(report.read_text())["help_count"] == 37
    assert "Wrote" in capsys.readouterr().out


def test_toml_configuration_and_passage_override(tmp_path):
    config = tmp_path / "reader.toml"
    config.write_text('name = "TOML edition"\npassage = "2:1-12"\n[layout]\npaper = "a5"\n')
    result = load_config(config, passage="2:3-9")
    assert result.name == "TOML edition"
    assert result.passage == "2:3-9"
    assert result.layout.paper == "a5"
