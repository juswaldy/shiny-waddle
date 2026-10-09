"""A bounded XeLaTeX compiler and measured, explicit page construction."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import time
from importlib.resources import files
from pathlib import Path

from pypdf import PdfReader

from .models import Cancelled, ReaderDocument, ReaderError, digest
from .render import escape_latex
from .sources import catalog

PAPERS = {
    "reader": (140, 216, 10),
    "reference": (180, 281, 10),
    "a4": (210, 297, 16),
    "a5": (148, 210, 10),
    "letter": (215.9, 279.4, 16),
}
PT_PER_MM = 72.27 / 25.4


def paper_dimensions(layout: dict) -> tuple[float, float, float]:
    if layout["paper"] == "custom":
        return layout["paper_width_mm"], layout["paper_height_mm"], 10
    return PAPERS[layout["paper"]]


def engine_path() -> str:
    explicit = os.environ.get("READER_XELATEX")
    candidates = [
        explicit,
        shutil.which("xelatex"),
        str(Path.cwd() / ".tools/.TinyTeX/bin/x86_64-linux/xelatex"),
    ]
    for value in candidates:
        if value and Path(value).is_file():
            return str(Path(value).absolute())
    raise ReaderError("XeLaTeX is not installed. Run scripts/bootstrap.sh or set READER_XELATEX.")


def font_path(name: str) -> Path:
    if name == "Ezra SIL":
        paths = [
            Path(str(files("bible_reader").joinpath("resources/SILEOT.ttf"))),
            Path.cwd() / ".tools/ezra/usr/share/fonts/truetype/ezra/SILEOT.ttf",
            Path("/usr/share/fonts/truetype/ezra/SILEOT.ttf"),
        ]
    else:
        paths = [Path.home() / ".fonts/SBL_Hbrw.ttf"]
    for path in paths:
        if path.is_file():
            return path
    if shutil.which("fc-match"):
        result = subprocess.run(
            ["fc-match", "--format", "%{family}|%{file}", name], capture_output=True, text=True, timeout=10
        )
        family, _, location = result.stdout.partition("|")
        if name in family and Path(location).is_file():
            return Path(location)
    raise ReaderError(f"The selected font {name} is missing. Install it or choose an installed font.")


class Compiler:
    def __init__(self, directory: Path, font: str, cancelled=lambda: False):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.engine = engine_path()
        self.cancelled = cancelled
        source = font_path(font)
        shutil.copyfile(source, self.directory / "reader-hebrew.ttf")
        self.font_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        self.environment = subprocess.run(
            [self.engine, "--version"], capture_output=True, text=True, timeout=10
        ).stdout.splitlines()[0]

    def compile(self, name: str, text: str, *, passes: int = 1):
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ReaderError("Invalid internal compilation name")
        (self.directory / f"{name}.tex").write_text(text, encoding="utf-8")
        environment = os.environ.copy()
        environment.update(
            {
                "openin_any": "p",
                "openout_any": "p",
                "SOURCE_DATE_EPOCH": "0",
                "FORCE_SOURCE_DATE": "1",
                "XDG_CACHE_HOME": str(self.directory / ".cache"),
            }
        )
        for _ in range(passes):
            if self.cancelled():
                raise Cancelled("Build cancelled")
            with (self.directory / f"{name}.console.log").open("wb") as output:
                process = subprocess.Popen(
                    [
                        self.engine,
                        "-no-shell-escape",
                        "-halt-on-error",
                        "-file-line-error",
                        "-recorder",
                        "-interaction=nonstopmode",
                        f"{name}.tex",
                    ],
                    cwd=self.directory,
                    env=environment,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                deadline = time.monotonic() + 90
                try:
                    while process.poll() is None:
                        if self.cancelled():
                            raise Cancelled("Build cancelled")
                        if time.monotonic() > deadline:
                            raise ReaderError("XeLaTeX exceeded the 90-second compilation limit")
                        time.sleep(0.05)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
            if process.returncode:
                log = (self.directory / f"{name}.console.log").read_text(errors="replace")
                if "Dimension too large" in log:
                    raise ReaderError(
                        "Layout overflow: the measured text and notes exceed TeX's dimension limit. Shorten reviewed glosses or reduce the passage."
                    )
                raise ReaderError(f"XeLaTeX failed; inspect {name}.console.log.\n{log[-1800:]}")
        log = (self.directory / f"{name}.log").read_text(errors="replace")
        if "Missing character:" in log:
            raise ReaderError("Selected fonts cannot render all characters. See the TeX log.")
        return log


def scripture_macros(layout: dict) -> str:
    if layout.get("verse_layout", "continuous") == "verse-per-line":
        return rf"""\newcommand{{\Scripture}}[1]{{#1}}
\newcommand{{\Verse}}[2]{{%
  \noindent\hbox to\linewidth{{%
    \vtop{{\hsize=\dimexpr\linewidth-6mm\relax
      \setRTL\hebrewfont\fontsize{{{layout["body_pt"]}}}{{{layout["leading_pt"]}}}\selectfont
      \parindent=0pt\leftskip=0pt plus 1fil\rightskip=0pt\parfillskip=0pt
      \noindent\strut #2\par}}%
    \hskip2mm\vtop{{\hsize=4mm\raggedleft\fontsize{{11}}{{{layout["leading_pt"]}}}\selectfont\strut #1\par}}%
  }}\par\vskip2pt
}}
\newcommand{{\ChapterOpen}}[4]{{%
  \vskip7pt\noindent\hbox to\linewidth{{%
    \vtop{{\hsize=\dimexpr\linewidth-14mm\relax\linewidth=\hsize\vskip0pt
      \Verse{{}}{{#2}}\Verse{{#3}}{{#4}}}}%
    \hskip2mm\vtop{{\hsize=12mm\vskip0pt
      \hbox{{\fboxsep=1pt\fbox{{\fbox{{\parbox[c][9mm][c]{{9mm}}{{\centering\fontsize{{25}}{{28}}\selectfont #1}}}}}}}}}}
  }}\par
}}
"""
    return rf"""\newif\ifChapterParagraph
\newcommand{{\EndScriptureParagraph}}{{%
  \par\ifChapterParagraph\ifnum\prevgraf<2\vskip{layout["leading_pt"]}pt\fi\fi
  \ChapterParagraphfalse
}}
\newcommand{{\Scripture}}[1]{{\begingroup
  \setRTL\hebrewfont\fontsize{{{layout["body_pt"]}}}{{{layout["leading_pt"]}}}\selectfont
  \parindent=0pt\leftskip=0pt\rightskip=0pt\parfillskip=0pt plus 1fil
  \tolerance=9999\emergencystretch=3em\noindent #1\EndScriptureParagraph\endgroup
}}
\newcommand{{\Verse}}[2]{{%
  \strut\textenglish{{\fontsize{{11}}{{{layout["leading_pt"]}}}\selectfont #1}}\nobreak\hspace{{0.35em}}#2%
}}
\newcommand{{\ChapterOpen}}[1]{{%
  \EndScriptureParagraph\vskip7pt\ChapterParagraphtrue\hangindent=-14mm\hangafter=-2\noindent
  \textenglish{{\makebox[0pt][l]{{\hspace{{2mm}}\smash{{\raisebox{{-2mm}}{{%
    \fboxsep=1pt\fbox{{\fbox{{\parbox[c][9mm][c]{{9mm}}{{\centering\fontsize{{25}}{{28}}\selectfont #1}}}}}}%
  }}}}}}}}%
}}
"""


def preamble(layout: dict) -> str:
    width, height, margin = paper_dimensions(layout)
    # Parameters are validated numeric values; external content is always escaped separately.
    return rf"""\documentclass{{article}}
\usepackage[paperwidth={width}mm,paperheight={height}mm,margin={margin}mm]{{geometry}}
\usepackage{{fontspec}}
\usepackage[unicode,hidelinks]{{hyperref}}
\usepackage{{polyglossia}}
\setdefaultlanguage{{english}}
\setotherlanguage{{hebrew}}
\setmainfont{{lmroman10-regular.otf}}[BoldFont=lmroman10-bold.otf,ItalicFont=lmroman10-italic.otf]
\newfontfamily\hebrewfont[Script=Hebrew]{{reader-hebrew.ttf}}
\pagestyle{{empty}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0pt}}
\setlength{{\fboxrule}}{{0.35pt}}
\hfuzz=0.2pt
{scripture_macros(layout)}
\newcommand{{\HelpMarker}}[2]{{\nobreak\textsuperscript{{\textenglish{{\fontsize{{7}}{{8}}\selectfont\hyperlink{{#1}}{{#2}}}}}}}}
\newcommand{{\ReadingMark}}[1]{{\nobreak\textsuperscript{{\textenglish{{\fontsize{{6}}{{7}}\selectfont #1}}}}}}
\newcommand{{\Note}}[5]{{\hypertarget{{#1}}{{}}\mbox{{\textsuperscript{{#2}}\texthebrew{{#3}}}}\nobreak\hspace{{0.2em}}#4#5.\hspace{{0.9em}}}}
\newcommand{{\Notes}}[1]{{\begingroup\setLTR\fontsize{{{layout["notes_pt"]}}}{{{layout["notes_pt"] * 1.35}}}\selectfont
  \raggedright\emergencystretch=3em #1\par\endgroup}}
\newcommand{{\Header}}[3]{{\hbox to\linewidth{{\rlap{{\fontsize{{10}}{{12}}\selectfont #1}}\hfil
  {{\hebrewfont\fontsize{{18}}{{20}}\selectfont #2}}\hfil\llap{{\fontsize{{10}}{{12}}\selectfont #3}}}}\vskip3pt\hrule height0.35pt\vskip9pt}}
\newbox\BodyBox
\newbox\NotesBox
\newwrite\Metrics
\begin{{document}}
"""


def word_tex(token: dict, document: ReaderDocument, prefix: str) -> str:
    result = escape_latex(token["surface"])
    if token["reading"] in {"ketiv", "qere"} and document.config["readings"] == "both":
        result += rf"\ReadingMark{{{token['reading'][0].upper()}}}"
    for identity in token["helps"]:
        note = document.helps[identity]
        result += rf"\HelpMarker{{{prefix}-{digest(identity)[:16]}}}{{{note['label']}}}"
    if token["kind"] == "word":
        return rf"\mbox{{{result}}}"
    return result


def verse_content(verse: dict, document: ReaderDocument, prefix: str):
    parts = []
    previous = None
    for token in verse["tokens"]:
        kind = token["kind"]
        if kind in {"x-pe", "x-samekh"}:
            parts.append(r"\quad " + word_tex(token, document, prefix))
        else:
            separator = " "
            if previous is None or kind in {"x-maqqef", "x-sof-pasuq"} or previous == "x-maqqef":
                separator = ""
            parts.append(separator + word_tex(token, document, prefix))
        previous = kind
    return "".join(parts)


def blocks(document: ReaderDocument):
    result = []
    index = 0
    while index < len(document.verses):
        verse = document.verses[index]
        group = [verse]
        if verse["verse"] == 1 and index + 1 < len(document.verses):
            nxt = document.verses[index + 1]
            if nxt["chapter"] == verse["chapter"] and nxt["verse"] == 2:
                group.append(nxt)
                index += 1
        result.append(group)
        index += 1
    return result


def contents(groups: list, document: ReaderDocument, prefix: str):
    scripture = []
    verses = [v for group in groups for v in group]
    if document.config["layout"].get("verse_layout", "continuous") == "verse-per-line":
        for group in groups:
            first = group[0]
            if first["verse"] == 1:
                second = group[1] if len(group) > 1 else None
                scripture.append(
                    rf"\ChapterOpen{{{first['chapter']}}}{{{verse_content(first, document, prefix)}}}"
                    + "{"
                    + (str(second["verse"]) if second else "")
                    + "}{"
                    + (verse_content(second, document, prefix) if second else "")
                    + "}"
                )
            else:
                scripture.append(rf"\Verse{{{first['verse']}}}{{{verse_content(first, document, prefix)}}}")
    else:
        for verse in verses:
            content = verse_content(verse, document, prefix)
            if verse["verse"] == 1:
                scripture.append(rf"\ChapterOpen{{{verse['chapter']}}}" + content)
            else:
                scripture.append(rf"\Verse{{{verse['verse']}}}{{{content}}}")
    note_ids = sorted(
        {h for v in verses for t in v["tokens"] for h in t["helps"]},
        key=lambda h: (document.helps[h]["chapter"], document.helps[h]["label"]),
    )
    notes = []
    chapter = None
    for identity in note_ids:
        note = document.helps[identity]
        if chapter is not None and chapter != note["chapter"]:
            notes.append(r"\par\vskip7pt\noindent\hspace*{1em}")
        chapter = note["chapter"]
        stem = (escape_latex(note["stem"]) + r"\enspace ") if note["stem"] else ""
        headword = "".join(c for c in note["headword"] if not ("\u0591" <= c <= "\u05af"))
        gloss = note["gloss"].rstrip(". ")
        notes.append(
            rf"\Note{{{prefix}-{digest(identity)[:16]}}}{{{note['label']}}}"
            + "{"
            + escape_latex(headword)
            + "}{"
            + stem
            + "}{"
            + escape_latex(gloss)
            + "}"
        )
    return r"\Scripture{" + "\n".join(scripture) + "}", r"\Notes{" + "\n".join(notes) + "}", note_ids


def measure_candidates(compiler: Compiler, candidates: list, document: ReaderDocument):
    body = [preamble(document.config["layout"]), r"\immediate\openout\Metrics=measure.metrics"]
    for index, candidate in enumerate(candidates):
        scripture, notes, _ = contents(candidate, document, f"measure{index}")
        body.extend(
            [
                "\\setbox\\BodyBox=\\vbox{\\hsize=\\linewidth\n" + scripture + "}\n",
                "\\setbox\\NotesBox=\\vbox{\\hsize=\\linewidth\n" + notes + "}\n",
                rf"\immediate\write\Metrics{{{index}|\number\dimexpr\ht\BodyBox+\dp\BodyBox\relax|\number\dimexpr\ht\NotesBox+\dp\NotesBox\relax}}",
            ]
        )
    body.extend([r"\immediate\closeout\Metrics", r"\end{document}"])
    compiler.compile("measure", "\n".join(body))
    result = []
    for line in (compiler.directory / "measure.metrics").read_text().splitlines():
        index, scripture, notes = map(int, line.split("|"))
        if index != len(result):
            raise ReaderError("TeX measurement records are out of order")
        result.append((scripture, notes))
    if len(result) != len(candidates):
        raise ReaderError("Missing TeX measurements")
    return result


def paginate(document: ReaderDocument, compiler: Compiler, progress=lambda _: None):
    layout = document.config["layout"]
    _, height, margin = paper_dimensions(layout)
    usable_pt = (height - 2 * margin) * PT_PER_MM
    # Header and separator spacing: deliberately conservative, final box is measured again.
    overhead_pt = 55
    budget_sp = int((usable_pt - overhead_pt) * 65536)
    remaining = blocks(document)
    plans = []
    while remaining:
        if compiler.cancelled():
            raise Cancelled("Build cancelled")
        progress(f"Measuring page {len(plans) + 1}")
        batch_size = int(usable_pt / layout["leading_pt"]) + 2
        candidates = []
        metrics = []
        # Run-in verses can share a line. Extend the initial measurement window
        # while its last prefix fits, rather than imposing a verse-per-line cap.
        while len(candidates) < len(remaining):
            start = len(candidates) + 1
            stop = min(len(remaining), len(candidates) + batch_size)
            batch = [remaining[:n] for n in range(start, stop + 1)]
            candidates.extend(batch)
            metrics.extend(measure_candidates(compiler, batch, document))
            if sum(metrics[-1]) > budget_sp:
                break
        fitting = [i for i, (text, notes) in enumerate(metrics) if text + notes <= budget_sp]
        if not fitting:
            raise ReaderError(
                f"Layout overflow at {remaining[0][0]['reference']}: a verse/opening and its notes cannot fit. Increase page size or shorten reviewed glosses."
            )
        chosen = max(fitting)
        groups = candidates[chosen]
        _, _, notes = contents(groups, document, f"p{len(plans) + 1}")
        verses = [v for g in groups for v in g]
        plans.append(
            {
                "page": len(plans) + 1,
                "folio": layout["first_folio"] + len(plans),
                "first": verses[0]["reference"],
                "last": verses[-1]["reference"],
                "references": [v["reference"] for v in verses],
                "help_ids": notes,
                "text_height_sp": metrics[chosen][0],
                "notes_height_sp": metrics[chosen][1],
                "budget_sp": budget_sp,
                "groups": groups,
            }
        )
        remaining = remaining[chosen + 1 :]
    return plans


def final_tex(document: ReaderDocument, plans: list):
    body = [preamble(document.config["layout"])]
    title = escape_latex(catalog()["books"][document.config["book"]]["hebrew"])
    for plan in plans:
        scripture, notes, _ = contents(plan["groups"], document, f"p{plan['page']}")
        first = plan["first"].split(".")
        last = plan["last"].split(".")
        passage = f"{first[-2]}:{first[-1]}"
        if first != last:
            passage += f"–{last[-2]}:{last[-1]}"
        body.append(r"\noindent\vbox to\textheight{\hsize=\linewidth")
        body.append(rf"\Header{{{passage}}}{{{title}}}{{{plan['folio']}}}")
        body.append(scripture)
        body.append(r"\vfil\vskip8pt\hrule height0.35pt\vskip5pt")
        body.append(notes)
        body.append(r"}\par\newpage")
    body.append(r"\raggedright\emergencystretch=3em\section*{Sources and edition}")
    body.append(escape_latex(document.config["name"]) + r"\par\bigskip")
    for notice in document.sources["attributions"] + document.sources["transformations"] + document.warnings:
        body.append(escape_latex(notice) + r"\par\medskip")
    body.append("Text revision: " + escape_latex(document.sources["oshb_revision"]) + r"\par")
    body.append("Lexicon revision: " + escape_latex(document.sources["step_revision"]) + r"\par")
    body.append(r"\end{document}")
    return "\n".join(body)


def verify_pdf(path: Path, plans: list, document: ReaderDocument, log: str):
    pdf = PdfReader(path)
    if len(pdf.pages) != len(plans) + 1:
        raise ReaderError(
            f"Unexpected PDF pagination: {len(pdf.pages)} pages, expected {len(plans)} reader pages and one credits page"
        )
    if re.search(r"Overfull \\[hv]box", log):
        raise ReaderError("The PDF has overflowing content; inspect reader.log and adjust the layout.")
    expected = [v["reference"] for v in document.verses]
    actual = [ref for p in plans for ref in p["references"]]
    if actual != expected:
        raise ReaderError("Page plan lost or duplicated verses")
    for plan in plans:
        used = {h for g in plan["groups"] for v in g for t in v["tokens"] for h in t["helps"]}
        if used != set(plan["help_ids"]):
            raise ReaderError("Page-local notes do not match their word anchors")
        page_index = plan["page"] - 1
        expected_links = sum(len(t["helps"]) for g in plan["groups"] for v in g for t in v["tokens"])
        links = [
            a.get_object()
            for a in pdf.pages[page_index].get("/Annots", [])
            if a.get_object().get("/A", {}).get("/S") == "/GoTo"
        ]
        if len(links) != expected_links:
            raise ReaderError("Compiled PDF marker count does not match the reader document")
        for link in links:
            target = str(link["/A"]["/D"])
            destination = pdf.named_destinations.get(target)
            if destination is None or pdf.get_destination_page_number(destination) != page_index:
                raise ReaderError("A compiled PDF lexical marker points to another page or a missing help")
        for font in pdf.pages[page_index]["/Resources"]["/Font"].values():
            font = font.get_object()
            descendants = font.get("/DescendantFonts", [font])
            for descendant in descendants:
                descriptor = descendant.get_object().get("/FontDescriptor")
                if descriptor is None or not any(
                    key in descriptor.get_object() for key in ("/FontFile", "/FontFile2", "/FontFile3")
                ):
                    raise ReaderError("A PDF font is not embedded")
    return {
        "reader_pages": len(plans),
        "credits_pages": 1,
        "total_pages": len(pdf.pages),
        "verse_count": len(expected),
        "help_count": len(document.helps),
        "page_membership": "verified",
        "pdf_marker_destinations": "verified",
        "fonts_embedded": True,
    }
