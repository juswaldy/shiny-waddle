import copy
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from bible_reader.__main__ import main as entrypoint
from bible_reader.cli import main
from bible_reader.data_files import load_reader_data
from bible_reader.editorial import build_document
from bible_reader.jobs import run_worker
from bible_reader.models import Decision, ProjectConfig, ReaderError
from bible_reader.service import build, build_from_data, compile_tex
from bible_reader.tex import verify_pdf
from bible_reader.web.app import create_app
from bible_reader.word_classes import WORD_CLASS_COLORS, word_color


@pytest.mark.integration
def test_reader_overflow_retains_pdf_bundle_and_all_validation_diagnostics(
    source_state, tmp_path, tex_available, monkeypatch
):
    from bible_reader import service

    render = service.final_tex

    def overflowing_tex(document, plans):
        return render(document, plans).replace(
            r"\end{document}",
            r"\noindent\hbox to 0pt{Synthetic layout overflow}\par\end{document}",
        )

    monkeypatch.setattr(service, "final_tex", overflowing_tex)
    output = tmp_path / "overflow"
    stages = []
    result = build(source_state, ProjectConfig(), output, stages.append)
    assert stages[-1] == "Completed with errors"
    assert result["errors"] and "Overfull" in result["errors"][0]
    # Log errors do not prevent the remaining independent PDF checks.
    assert result["pdf_marker_destinations"] == "verified" and result["fonts_embedded"]
    checks = json.loads((output / "layout-diagnostics.json").read_text())
    assert checks["errors"] == result["errors"]
    assert json.loads((output / "manifest.json").read_text())["checks"] == checks
    with zipfile.ZipFile(output / "reader-bundle.zip") as bundle:
        assert {"reader.pdf", "reader.tex", "reader.log", "layout-diagnostics.json"} <= set(bundle.namelist())


@pytest.mark.integration
def test_standalone_pdf_with_overflow_finishes_and_cli_reports_failure(tmp_path, tex_available, capsys):
    text = (
        r"\documentclass{article}\begin{document}"
        r"\noindent\hbox to 0pt{Synthetic overflow}\par\end{document}"
    )
    source = tmp_path / "input.tex"
    source.write_text(text)
    output = tmp_path / "pdf"
    assert main(["transform", "tex-to-pdf", "--input", str(source), "--output", str(output)]) == 1
    assert '"errors"' in capsys.readouterr().out
    assert (output / "reader-bundle.zip").is_file()
    assert "overflowing content" in (output / "layout-diagnostics.json").read_text()


def test_data_export_needs_no_tex_and_preserves_complete_snapshot(source_state, tmp_path, monkeypatch):
    def no_compiler(*args, **kwargs):
        pytest.fail("Data export must not initialize TeX")

    monkeypatch.setattr("bible_reader.service.Compiler", no_compiler)
    config = ProjectConfig(lexicon_appendix=True)
    original = json.loads(json.dumps(build_document(source_state, config).json()))
    result = build(source_state, config, tmp_path / "data", emit="data")
    saved = json.loads((tmp_path / "data/reader.v2.json").read_text())
    assert saved == original
    assert load_reader_data(saved).json() == saved
    assert result["unresolved_helps"] == 0
    assert "reader.tex" not in result["artifacts"] and "reader.pdf" not in result["artifacts"]
    with zipfile.ZipFile(tmp_path / "data/reader-bundle.zip") as bundle:
        assert json.loads(bundle.read("reader.v2.json")) == original
    with pytest.raises(ReaderError, match="not empty"):
        build(source_state, config, tmp_path / "data", emit="data")


@pytest.mark.parametrize("mode", ["auto", "word-class"])
@pytest.mark.parametrize("overrides", [{}, {"noun": "#123abc", "name": "auto"}])
def test_data_export_pins_presets_and_preserves_color_overrides(
    source_state, tmp_path, monkeypatch, mode, overrides
):
    config = ProjectConfig(layout={"word_colors": mode, "word_color_overrides": overrides})
    document = build_document(source_state, config)
    original = copy.deepcopy(document.config)
    before = {category: word_color(category, document.config["layout"]) for category in WORD_CLASS_COLORS}
    build(source_state, config, tmp_path / "palette", emit="data")
    saved = json.loads((tmp_path / "palette/reader.v2.json").read_text())
    palette = saved["config"]["layout"]["word_color_overrides"]
    assert set(palette) == set(WORD_CLASS_COLORS)
    assert palette["verb"] == "#A33432"
    assert palette["noun"] == ("#123ABC" if overrides else "#245A81")
    assert palette["name"] == ("auto" if overrides else "#9C3776")
    assert saved["config"]["layout"]["word_colors"] == mode
    assert config.model_dump() == document.config == original
    assert document.json() == saved
    assert document.config == original  # Serializing never changes the project palette.
    with zipfile.ZipFile(tmp_path / "palette/reader-bundle.zip") as bundle:
        assert json.loads(bundle.read("reader.v2.json")) == saved
    # A later application palette must not change a saved reader's appearance.
    monkeypatch.setitem(WORD_CLASS_COLORS, "verb", ("Verbs", "010203"))
    monkeypatch.setitem(WORD_CLASS_COLORS, "noun", ("Nouns", "040506"))
    restored = load_reader_data(saved)
    assert restored.json() == saved
    assert {
        category: word_color(category, restored.config["layout"]) for category in WORD_CLASS_COLORS
    } == before


def test_unresolved_data_can_be_saved_but_cannot_render(source_state, consonant_review, tmp_path):
    config = ProjectConfig(selection="all", passage="1:1")
    result = build(source_state, config, tmp_path / "data", emit="data")
    assert result["unresolved_helps"] > 0
    saved = json.loads((tmp_path / "data/reader.v2.json").read_text())
    with pytest.raises(ReaderError, match="unresolved selected helps"):
        build_from_data(tmp_path / "offline", saved, tmp_path / "tex")


def test_manual_gloss_data_round_trip_and_reader_export(
    source_state, consonant_review, tmp_path, tex_available
):
    config = ProjectConfig(selection="all", passage="3:1", lexicon_appendix=True)
    config.decisions = {
        row["anchor"]: Decision(gloss="Synthetic manual help: 50% & review")
        if row["anchor"] == "test-unmatched:0"
        else Decision(action="exclude")
        for row in build_document(source_state, config).review
    }
    result = build(source_state, config, tmp_path / "data", emit="data")
    assert result["unresolved_helps"] == 0
    saved = json.loads((tmp_path / "data/reader.v2.json").read_text())
    assert load_reader_data(saved).json() == saved
    help = next(iter(saved["helps"].values()))
    assert help["status"] == "editorial" and help["editorial"] and help["entry_id"] is None
    assert saved["lexicon_appendix"][0]["gloss"] == help["gloss"]
    result = build_from_data(tmp_path / "offline", saved, tmp_path / "pdf", emit="pdf")
    assert "reader.pdf" in result["artifacts"]
    assert r"50\% \& review" in (tmp_path / "pdf/reader.tex").read_text()


def test_reader_data_rejects_broken_references_and_tex_in_numeric_fields(source_state):
    original = json.loads(json.dumps(build_document(source_state, ProjectConfig()).json()))
    malformed = []
    data = copy.deepcopy(original)
    data["schema_version"] = 1
    malformed.append(data)
    data = copy.deepcopy(original)
    next(iter(data["helps"].values()))["label"] = r"\input{outside}"
    malformed.append(data)
    data = copy.deepcopy(original)
    data["verses"][0]["tokens"][0]["helps"] = ["missing-help"]
    malformed.append(data)
    data = copy.deepcopy(original)
    data["review"] = []
    malformed.append(data)
    data = copy.deepcopy(original)
    data["verses"][0]["chapter"] = "1"
    malformed.append(data)
    data = copy.deepcopy(original)
    data["sources"]["notices"] = {"bad": {"filename": "../reader.tex", "sha256": "0" * 64}}
    malformed.append(data)
    for data in malformed:
        with pytest.raises(ReaderError, match="Invalid reader data file"):
            load_reader_data(data)


def test_reader_data_rejects_duplicate_labels_even_with_matching_help_records(source_state):
    data = json.loads(json.dumps(build_document(source_state, ProjectConfig()).json()))
    first, second = [help for help in data["helps"].values() if help["chapter"] == 1][:2]
    data["registry"]["1"][second["id"]] = second["label"] = first["label"]
    for row in data["review"]:
        if row["help_id"] == second["id"]:
            row["label"] = first["label"]
    with pytest.raises(ReaderError, match="Help labels must be unique within each chapter"):
        load_reader_data(data)


def test_reader_data_rejects_duplicate_registry_labels_outside_the_passage(source_state):
    data = json.loads(json.dumps(build_document(source_state, ProjectConfig()).json()))
    # A chapter registry includes slots not referenced by the current passage.
    label = next(iter(data["registry"]["1"].values()))
    data["registry"]["1"]["Prov.1:outside-passage"] = label
    with pytest.raises(ReaderError, match="Help labels must be unique within each chapter"):
        load_reader_data(data)


def test_reader_data_allows_label_reuse_across_chapters_and_repeated_help_anchors(source_state):
    config = ProjectConfig(selection="all", gloss_selection="first-entry")
    data = json.loads(json.dumps(build_document(source_state, config).json()))
    assert set(data["registry"]["1"].values()) & set(data["registry"]["2"].values())
    anchors = [help_id for verse in data["verses"] for token in verse["tokens"] for help_id in token["helps"]]
    assert len(anchors) > len(set(anchors))  # Multiple tokens may refer to one semantic help.
    assert load_reader_data(data).json() == data


def test_cli_source_to_data_and_invalid_transform_input(source_state, tmp_path, monkeypatch):
    output = tmp_path / "data"
    assert main(["--state", str(source_state), "build", "--emit", "data", "--output", str(output)]) == 0
    assert (output / "reader.v2.json").is_file()
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": 1}')
    monkeypatch.setattr(
        "sys.argv",
        ["bible-reader", "transform", "data-to-tex", "--input", str(bad), "--output", str(tmp_path / "tex")],
    )
    with pytest.raises(SystemExit) as error:
        entrypoint()
    assert error.value.code == 1
    assert not (tmp_path / "tex").exists()


def test_api_data_export_download_and_upload_snapshots(source_state):
    app = create_app(source_state, start_worker=False)
    with TestClient(app) as client:
        client.headers["X-Reader-Token"] = app.state.csrf_token
        project = client.post("/api/projects", json={}).json()
        base = f"/api/projects/{project['id']}"
        job = client.post(base + "/data")
        assert job.status_code == 202
        run_worker(source_state, once=True)
        job = client.get(f"/api/jobs/{job.json()['id']}").json()
        assert job["status"] == "succeeded"
        download = client.get(f"/api/jobs/{job['id']}/artifacts/reader.v2.json?download=true")
        assert "attachment" in download.headers["content-disposition"]
        data = download.json()
        upload = client.post(base + "/transforms/data-to-tex", json={"data": data})
        assert upload.status_code == 202
        uploaded = upload.json()
        path = source_state / "inputs" / uploaded["config"]["input_file"]
        assert json.loads(path.read_text()) == data
        assert "data" not in uploaded["config"]  # Polling never returns a full uploaded file.
        client.post(f"/api/jobs/{uploaded['id']}/cancel")
        tex = r"\documentclass{article}\begin{document}Hello\end{document}"
        upload = client.post(base + "/transforms/tex-to-pdf", json={"tex": tex})
        assert upload.status_code == 202
        uploaded = upload.json()
        assert (source_state / "inputs" / uploaded["config"]["input_file"]).read_text() == tex
        assert client.get(base).json() == project
        assert client.post(base + "/transforms/data-to-tex", json={"data": {}}).status_code == 400
        assert client.post(base + "/transforms/tex-to-pdf", json={"tex": ""}).status_code == 400


@pytest.mark.integration
@pytest.mark.parametrize("language", ["hebrew", "greek"])
def test_saved_data_to_tex_to_pdf_is_offline_and_preserves_reader(
    source_state, request, tmp_path, tex_available, language
):
    state = request.getfixturevalue("greek_state") if language == "greek" else source_state
    config = (
        ProjectConfig(book="John", passage="1:1-3", selection="all", gloss_selection="first-entry")
        if language == "greek"
        else ProjectConfig()
    )
    config.layout.word_colors = "word-class"
    config.layout.word_color_overrides = {"noun": "#123ABC", "name": "auto"}
    build(state, config, tmp_path / "data", emit="data")
    value = json.loads((tmp_path / "data/reader.v2.json").read_text())
    offline = tmp_path / "no-installed-sources"
    tex_result = build_from_data(offline, value, tmp_path / "tex")
    assert "reader.tex" in tex_result["artifacts"] and "reader.pdf" not in tex_result["artifacts"]
    assert json.loads((tmp_path / "tex/reader.v2.json").read_text()) == value
    text = (tmp_path / "tex/reader.tex").read_text()
    assert r"\textcolor[HTML]{123ABC}" in text
    result = compile_tex(text, tmp_path / "pdf")
    assert result["fonts_embedded"]
    assert "page_membership" not in result  # Standalone TeX does not claim a reader-specific check.
    assert (tmp_path / "pdf/reader.tex").read_text() == text
    plans = json.loads((tmp_path / "tex/page-plan.json").read_text())
    checked = verify_pdf(
        tmp_path / "pdf/reader.pdf", plans, load_reader_data(value), (tmp_path / "pdf/reader.log").read_text()
    )
    assert checked["pdf_marker_destinations"] == "verified"
    assert not offline.exists()
