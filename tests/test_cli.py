import json

import pytest

from bible_reader.cli import load_config, main
from bible_reader.models import Layout


def test_init_refuses_overwrite_and_inspect_is_offline(source_state, tmp_path, capsys):
    config = tmp_path / "project.json"
    assert main(["init", "--project", str(config)]) == 0
    original = config.read_bytes()
    assert json.loads(original)["layout"]["verse_layout"] == "continuous"
    assert json.loads(original)["layout"]["paper"] == "reader"
    assert json.loads(original)["layout"]["word_colors"] == "auto"
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
    config.write_text(
        'name = "TOML edition"\npassage = "2:1-12"\n[layout]\npaper = "a5"\nverse_layout = "verse-per-line"\n'
    )
    result = load_config(config, passage="2:3-9")
    assert result.name == "TOML edition"
    assert result.passage == "2:3-9"
    assert result.layout.paper == "a5"
    assert result.layout.verse_layout == "verse-per-line"


def test_legacy_project_defaults_and_invalid_verse_layout(tmp_path):
    config = tmp_path / "legacy.json"
    config.write_text('{"layout": {"paper": "a5"}}')
    assert load_config(config).layout.verse_layout == "continuous"
    assert load_config(config).layout.word_colors == "auto"
    assert load_config(config).gloss_selection == "reviewed"
    with pytest.raises(ValueError):
        Layout(verse_layout="unknown")


@pytest.mark.parametrize("policy", ["reviewed", "first-entry"])
def test_gloss_selection_in_json_and_toml(tmp_path, policy):
    json_config = tmp_path / "glosses.json"
    json_config.write_text(json.dumps({"gloss_selection": policy}))
    toml_config = tmp_path / "glosses.toml"
    toml_config.write_text(f'gloss_selection = "{policy}"\n')
    assert load_config(json_config) == load_config(toml_config)
    assert load_config(json_config).gloss_selection == policy


def test_word_color_settings_in_json_and_toml(tmp_path):
    json_config = tmp_path / "colors.json"
    json_config.write_text(
        json.dumps(
            {
                "layout": {
                    "word_colors": "word-class",
                    "word_color_overrides": {"noun": "#112233", "name": "auto"},
                }
            }
        )
    )
    toml_config = tmp_path / "colors.toml"
    toml_config.write_text(
        '[layout]\nword_colors = "word-class"\n[layout.word_color_overrides]\nnoun = "#112233"\nname = "auto"\n'
    )
    assert load_config(json_config) == load_config(toml_config)
    assert load_config(json_config).layout.word_color_overrides == {"noun": "#112233", "name": "auto"}
    with pytest.raises(ValueError):
        Layout(word_colors="unknown")


def test_custom_paper_in_json_and_toml(tmp_path):
    json_config = tmp_path / "custom.json"
    json_config.write_text(
        '{"layout": {"paper": "custom", "paper_width_mm": 160.5, "paper_height_mm": 230.25}}'
    )
    toml_config = tmp_path / "custom.toml"
    toml_config.write_text('[layout]\npaper = "custom"\npaper_width_mm = 160.5\npaper_height_mm = 230.25\n')
    first = load_config(json_config)
    assert first == load_config(toml_config)
    assert first.layout.paper == "custom"
    assert first.layout.paper_width_mm == 160.5
    assert first.layout.paper_height_mm == 230.25
    assert load_config(None).layout.paper == "reader"


@pytest.mark.parametrize("policy", ["consonants-only", "consonants", "consonants-maqqef-sof-pasuq"])
def test_consonant_policy_in_json_and_toml(tmp_path, policy):
    json_config = tmp_path / "consonants.json"
    json_config.write_text(json.dumps({"cantillation": policy}))
    toml_config = tmp_path / "consonants.toml"
    toml_config.write_text(f'cantillation = "{policy}"\n')
    assert load_config(json_config) == load_config(toml_config)
    assert load_config(json_config).cantillation == policy
    assert load_config(None).cantillation == "hide"


@pytest.mark.parametrize(
    "dimensions",
    [
        {},
        {"paper_width_mm": 140},
        {"paper_height_mm": 216},
        {"paper_width_mm": 0, "paper_height_mm": 216},
        {"paper_width_mm": 140, "paper_height_mm": -1},
        {"paper_width_mm": 20, "paper_height_mm": 216},
        {"paper_width_mm": 140, "paper_height_mm": 1001},
        {"paper_width_mm": float("nan"), "paper_height_mm": 216},
        {"paper_width_mm": 140, "paper_height_mm": float("inf")},
        {"paper_width_mm": True, "paper_height_mm": 216},
        {"paper_width_mm": "140", "paper_height_mm": 216},
    ],
)
def test_invalid_custom_paper_is_rejected(dimensions):
    with pytest.raises(ValueError):
        Layout(paper="custom", **dimensions)
