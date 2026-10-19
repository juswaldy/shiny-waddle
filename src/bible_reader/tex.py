"""A bounded XeLaTeX compiler and measured, explicit page construction."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from pypdf import PdfReader

from .models import Cancelled, ReaderDocument, ReaderError, digest
from .render import escape_latex
from .sources import catalog
from .word_classes import word_color

PAPERS = {
    "reader": (140, 216, 10),
    "reference": (180, 281, 10),
    "a4": (210, 297, 16),
    "a5": (148, 210, 10),
    "letter": (215.9, 279.4, 16),
}
PT_PER_MM = 72.27 / 25.4


@dataclass(frozen=True)
class PageMeasurement:
    text_height_sp: int
    notes_height_sp: int
    page_height_sp: int
    usable_height_sp: int
    chapter_lines: int = 0

    @property
    def fits(self):
        return self.page_height_sp <= self.usable_height_sp

    @property
    def budget_sp(self):
        overhead = self.page_height_sp - self.text_height_sp - self.notes_height_sp
        return self.usable_height_sp - overhead


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
    if name == "Gentium Plus":
        paths = [Path(str(files("bible_reader").joinpath("resources/GentiumPlus-Regular.ttf")))]
    elif name == "Ezra SIL":
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
    def __init__(self, directory: Path, font: str, cancelled=lambda: False, *, greek=False):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.engine = engine_path()
        self.cancelled = cancelled
        source = font_path(font)
        shutil.copyfile(source, self.directory / "reader-hebrew.ttf")
        self.font_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        self.greek_font_hash = None
        if greek:
            greek_source = font_path("Gentium Plus")
            shutil.copyfile(greek_source, self.directory / "reader-greek.ttf")
            self.greek_font_hash = hashlib.sha256(greek_source.read_bytes()).hexdigest()
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
  }}\par\vskip0.8pt
}}
\newcommand{{\ChapterOpen}}[4]{{%
  \vskip4pt\noindent\hbox to\linewidth{{%
    \vtop{{\hsize=\dimexpr\linewidth-14mm\relax\linewidth=\hsize\vskip0pt
      \Verse{{}}{{#2}}\Verse{{#3}}{{#4}}}}%
    \hskip2mm\vtop{{\hsize=12mm\vskip0pt
      \hbox{{\fboxsep=1pt\fbox{{\fbox{{\parbox[c][9mm][c]{{9mm}}{{\centering\fontsize{{25}}{{28}}\selectfont #1}}}}}}}}}}
  }}\par
}}
"""
    return rf"""\newif\ifChapterParagraph
\newcommand{{\EndScriptureParagraph}}{{%
  \par\global\ChapterLines=0
  \ifChapterParagraph\global\ChapterLines=\prevgraf
    \ifnum\prevgraf<2\vskip{layout["leading_pt"]}pt\fi\fi
  \ChapterParagraphfalse
}}
\newcommand{{\Scripture}}[2][0]{{\begingroup
  \setRTL\hebrewfont\fontsize{{{layout["body_pt"]}}}{{{layout["leading_pt"]}}}\selectfont
  \parindent=0pt\leftskip=0pt\rightskip=0pt\parfillskip=0pt plus 1fil
  \tolerance=9999\emergencystretch=3em\noindent #2%
  \ifnum#1=1\parfillskip=0pt\fi\EndScriptureParagraph\endgroup
}}
\newcommand{{\Verse}}[2]{{%
  \strut\textenglish{{\fontsize{{11}}{{{layout["leading_pt"]}}}\selectfont #1}}\nobreak\hspace{{0.35em}}#2%
}}
\newcommand{{\ChapterOpen}}[1]{{%
  \EndScriptureParagraph\vskip4pt\ChapterParagraphtrue\hangindent=-14mm\hangafter=-2\noindent
  \textenglish{{\makebox[0pt][l]{{\hspace{{2mm}}\smash{{\raisebox{{-2mm}}{{%
    \fboxsep=1pt\fbox{{\fbox{{\parbox[c][9mm][c]{{9mm}}{{\centering\fontsize{{25}}{{28}}\selectfont #1}}}}}}%
  }}}}}}}}%
}}
"""


def greek_scripture_macros(layout: dict) -> str:
    badge = r"\newcommand{\ChapterBadge}[1]{\fboxsep=1pt\fbox{\fbox{\parbox[c][9mm][c]{9mm}{\centering\fontsize{25}{28}\selectfont #1}}}}"
    if layout.get("verse_layout", "continuous") == "verse-per-line":
        return (
            badge
            + rf"""
\newcommand{{\Scripture}}[1]{{#1}}
\newcommand{{\Verse}}[2]{{%
  \noindent\hbox to\linewidth{{%
    \vtop{{\hsize=4mm\raggedright\fontsize{{11}}{{{layout["leading_pt"]}}}\selectfont\strut #1\par}}\hskip2mm
    \vtop{{\hsize=\dimexpr\linewidth-6mm\relax
      \setLTR\greekfont\fontsize{{{layout["body_pt"]}}}{{{layout["leading_pt"]}}}\selectfont
      \parindent=0pt\leftskip=0pt\rightskip=0pt plus 1fil\parfillskip=0pt
      \noindent\strut #2\par}}%
  }}\par\vskip0.8pt
}}
\newcommand{{\ChapterOpen}}[4]{{%
  \vskip4pt\noindent\hbox to\linewidth{{%
    \vtop{{\hsize=12mm\vskip0pt\hbox{{\ChapterBadge{{#1}}}}}}\hskip2mm
    \vtop{{\hsize=\dimexpr\linewidth-14mm\relax\linewidth=\hsize\vskip0pt
      \Verse{{}}{{#2}}\Verse{{#3}}{{#4}}}}%
  }}\par
}}
"""
        )
    return (
        badge
        + rf"""
\newif\ifChapterParagraph
\newcommand{{\EndScriptureParagraph}}{{%
  \par\global\ChapterLines=0
  \ifChapterParagraph\global\ChapterLines=\prevgraf
    \ifnum\prevgraf<2\vskip{layout["leading_pt"]}pt\fi\fi
  \ChapterParagraphfalse\parshape=0
}}
\newcommand{{\Scripture}}[2][0]{{\begingroup
  \setLTR\greekfont\fontsize{{{layout["body_pt"]}}}{{{layout["leading_pt"]}}}\selectfont
  \parindent=0pt\leftskip=0pt\rightskip=0pt\parfillskip=0pt plus 1fil
  \tolerance=9999\emergencystretch=3em\noindent #2%
  \ifnum#1=1\parfillskip=0pt\fi\EndScriptureParagraph\endgroup
}}
\newcommand{{\Verse}}[2]{{%
  \strut\textenglish{{\fontsize{{11}}{{{layout["leading_pt"]}}}\selectfont #1}}\nobreak\hspace{{0.35em}}#2%
}}
\newcommand{{\ChapterOpen}}[1]{{%
  \EndScriptureParagraph\vskip4pt\ChapterParagraphtrue
  \parshape=3 14mm \dimexpr\linewidth-14mm\relax 14mm \dimexpr\linewidth-14mm\relax 0pt \linewidth
  \noindent\textenglish{{\makebox[0pt][r]{{\smash{{\raisebox{{-2mm}}{{\ChapterBadge{{#1}}}}}}\hspace{{2mm}}}}}}%
}}
"""
    )


def document_language(document: ReaderDocument) -> str:
    return document.sources.get("language", "hbo")


def preamble(layout: dict, *, lexicon_appendix=False, language="hbo") -> str:
    width, height, margin = paper_dimensions(layout)
    appendix_package = r"\usepackage{multicol}" if lexicon_appendix else ""
    # All scripture words are atomic boxes, so Greek hyphenation is unnecessary.
    # Use explicit script/font/direction runs even in minimal TeX installations.
    greek_setup = (
        r"\newfontfamily\greekfont[Script=Greek]{reader-greek.ttf}"
        r"\newcommand{\ReaderGreek}[1]{{\setLTR\greekfont #1}}"
        if language == "grc"
        else ""
    )
    headword_command = "ReaderGreek" if language == "grc" else "texthebrew"
    macros = greek_scripture_macros(layout) if language == "grc" else scripture_macros(layout)
    # Parameters are validated numeric values; external content is always escaped separately.
    return rf"""\documentclass{{article}}
\usepackage[paperwidth={width}mm,paperheight={height}mm,margin={margin}mm]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{graphicx}}
\usepackage{{xcolor}}
\usepackage[unicode,hidelinks]{{hyperref}}
{appendix_package}
\usepackage{{polyglossia}}
\setdefaultlanguage{{english}}
\setotherlanguage{{hebrew}}
\setmainfont{{lmroman10-regular.otf}}[BoldFont=lmroman10-bold.otf,ItalicFont=lmroman10-italic.otf]
\newfontfamily\hebrewfont[Script=Hebrew]{{reader-hebrew.ttf}}
{greek_setup}
\newfontfamily\booktitlefont{{lmromancaps10-regular.otf}}
\pagestyle{{empty}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0pt}}
\setlength{{\fboxrule}}{{0.35pt}}
\hfuzz=0.2pt
{macros}
\newcommand{{\HelpMarker}}[2]{{\nobreak\textsuperscript{{\textenglish{{\fontsize{{7}}{{8}}\selectfont\hyperlink{{#1}}{{#2}}}}}}}}
\newcommand{{\ReadingMark}}[1]{{\nobreak\textsuperscript{{\textenglish{{\fontsize{{6}}{{7}}\selectfont #1}}}}}}
\newcommand{{\NoteStem}}[1]{{\textenglish{{{{\fontsize{{{layout["notes_pt"] * 0.5}}}{{{layout["notes_pt"] * 1.15}}}\selectfont #1}}}}\hspace{{0.3em}}}}
\newcommand{{\Note}}[5]{{\hypertarget{{#1}}{{}}\mbox{{\textsuperscript{{#2}}\{headword_command}{{#3}}}}\nobreak\hspace{{0.2em}}#4#5.\hspace{{0.45em plus 0.1em minus 0.1em}}\ignorespaces}}
\newcommand{{\Notes}}[1]{{\begingroup\setLTR\fontsize{{{layout["notes_pt"]}}}{{{layout["notes_pt"] * 1.15}}}\selectfont
  \raggedright\lineskip=0.5pt\tolerance=9999\emergencystretch=3em\noindent #1\par\endgroup}}
\newsavebox{{\BookTitleBox}}
\newcommand{{\HebrewBookTitle}}[1]{{\texthebrew{{\fontsize{{18}}{{20}}\selectfont #1}}}}
% Match the English caps to the selected Hebrew font's full title height.
\newcommand{{\EnglishBookTitle}}[2]{{\begingroup
  \sbox{{\BookTitleBox}}{{\HebrewBookTitle{{#1}}}}%
  \raisebox{{-\dp\BookTitleBox}}{{\resizebox*{{!}}{{\dimexpr\ht\BookTitleBox+\dp\BookTitleBox\relax}}{{%
    \textenglish{{\booktitlefont\fontsize{{18}}{{20}}\selectfont #2}}}}}}%
\endgroup}}
\newcommand{{\Header}}[3]{{\hbox to\linewidth{{\rlap{{\fontsize{{10}}{{12}}\selectfont #1}}\hfil
  #2\hfil\llap{{\fontsize{{10}}{{12}}\selectfont #3}}}}\vskip3pt\hrule height0.35pt\vskip9pt}}
\newbox\BodyBox
\newbox\NotesBox
\newbox\PageBox
\newcommand{{\ReaderPage}}[3]{{%
  \Header{{#1}}{{#2}}{{#3}}%
  \copy\BodyBox\vskip9pt\hrule height0.35pt\vskip3pt
  \copy\NotesBox\vfil\kern0pt
}}
\newwrite\Metrics
\newcount\ChapterLines
\begin{{document}}
"""


def word_tex(token: dict, document: ReaderDocument, prefix: str) -> str:
    result = escape_latex(token["surface"])
    color = word_color(token.get("word_class"), document.config["layout"])
    if token["kind"] == "word" and color:
        result = rf"\textcolor[HTML]{{{color[1:]}}}{{{result}}}"
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
        # Hidden punctuation remains in source records without affecting spacing.
        if not token["surface"]:
            continue
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


def split_points(verse: dict) -> list[int]:
    """Legal word boundaries; keep maqaf chains and source reading pairs intact."""
    tokens = verse["tokens"]
    result = []
    previous = None
    for index, token in enumerate(tokens):
        if not token["surface"]:
            continue
        if (
            previous is not None
            and token["kind"] == "word"
            and previous["kind"] != "x-maqqef"
            and not (previous["reading"] == "ketiv" and token["reading"] == "qere")
        ):
            result.append(index)
        previous = token
    return result


def split_verse(verse: dict, index: int) -> tuple[dict, dict]:
    start = verse.get("token_start", 0)
    end = verse.get("token_end", start + len(verse["tokens"]))
    return (
        {**verse, "tokens": verse["tokens"][:index], "token_start": start, "token_end": start + index},
        {
            **verse,
            "tokens": verse["tokens"][index:],
            "token_start": start + index,
            "token_end": end,
            "continued": True,
        },
    )


def split_group(group: list[dict]) -> list[tuple[list[dict], list[dict]]]:
    """Prefixes of a verse or chapter opening, retaining all source fragments."""
    result = []
    for index, verse in enumerate(group):
        if index:
            result.append((group[:index], group[index:]))
        for point in split_points(verse):
            head, tail = split_verse(verse, point)
            result.append((group[:index] + [head], [tail] + group[index + 1 :]))
    return result


def continues_chapter(groups: list, document: ReaderDocument) -> bool:
    last = groups[-1][-1]
    for index, verse in enumerate(document.verses):
        if verse["reference"] == last["reference"]:
            if last.get("token_end", len(last["tokens"])) < len(verse["tokens"]):
                return True
            return (
                index + 1 < len(document.verses) and document.verses[index + 1]["chapter"] == last["chapter"]
            )
    raise ReaderError("Page fragment has an unknown source reference")


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
            if verse.get("continued"):
                scripture.append(content)
            elif verse["verse"] == 1:
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
            notes.append(r"\par\vskip3pt\noindent\hspace*{1em}")
        chapter = note["chapter"]
        stem = rf"\NoteStem{{{escape_latex(note['stem'].upper())}}}" if note["stem"] else ""
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
    run_in = document.config["layout"].get("verse_layout", "continuous") == "continuous"
    command = r"\Scripture[1]{" if run_in and continues_chapter(groups, document) else r"\Scripture{"
    return command + "\n".join(scripture) + "}", r"\Notes{" + "\n".join(notes) + "}", note_ids


def page_tex(groups: list, document: ReaderDocument, prefix: str, folio: int):
    scripture, notes, _ = contents(groups, document, prefix)
    first = groups[0][0]["reference"].split(".")
    last = groups[-1][-1]["reference"].split(".")
    passage = f"{first[-2]}:{first[-1]}"
    if first != last:
        passage += f"–{last[-2]}:{last[-1]}"
    book = catalog()["books"][document.config["book"]]
    if document_language(document) == "grc":
        title = (
            rf"\textenglish{{\booktitlefont\fontsize{{18}}{{20}}\selectfont {escape_latex(book['title'])}}}"
        )
    else:
        title = (
            rf"\HebrewBookTitle{{{escape_latex(book['hebrew'])}}}"
            if folio % 2
            else rf"\EnglishBookTitle{{{escape_latex(book['hebrew'])}}}{{{escape_latex(book['title'])}}}"
        )
    boxes = (
        "\\setbox\\BodyBox=\\vbox{\\hsize=\\linewidth\n" + scripture + "}\n"
        "\\setbox\\NotesBox=\\vbox{\\hsize=\\linewidth\n" + notes + "}\n"
    )
    return boxes, rf"\ReaderPage{{{passage}}}{{{title}}}{{{folio}}}"


def measure_candidates(compiler: Compiler, candidates: list, document: ReaderDocument, folio: int):
    body = [
        preamble(
            document.config["layout"],
            lexicon_appendix=document.config.get("lexicon_appendix", False)
            or document.config.get("lexicon_only", False),
            language=document_language(document),
        ),
        r"\immediate\openout\Metrics=measure.metrics",
    ]
    for index, candidate in enumerate(candidates):
        boxes, page = page_tex(candidate, document, f"measure{index}", folio)
        body.extend(
            [
                boxes,
                r"\setbox\PageBox=\vbox{\hsize=\linewidth " + page + "}",
                rf"\immediate\write\Metrics{{{index}|\number\dimexpr\ht\BodyBox+\dp\BodyBox\relax|\number\dimexpr\ht\NotesBox+\dp\NotesBox\relax|\number\dimexpr\ht\PageBox+\dp\PageBox\relax|\number\textheight|\number\ChapterLines}}",
            ]
        )
    body.extend([r"\immediate\closeout\Metrics", r"\end{document}"])
    compiler.compile("measure", "\n".join(body))
    result = []
    for line in (compiler.directory / "measure.metrics").read_text().splitlines():
        index, scripture, notes, page, usable, chapter_lines = map(int, line.split("|"))
        if index != len(result):
            raise ReaderError("TeX measurement records are out of order")
        result.append(PageMeasurement(scripture, notes, page, usable, chapter_lines))
    if len(result) != len(candidates):
        raise ReaderError("Missing TeX measurements")
    return result


def page_plan(groups: list, document: ReaderDocument, measurement: PageMeasurement, page: int, folio: int):
    _, _, notes = contents(groups, document, f"p{page}")
    verses = [verse for group in groups for verse in group]
    return {
        "page": page,
        "folio": folio,
        "first": verses[0]["reference"],
        "last": verses[-1]["reference"],
        "references": [verse["reference"] for verse in verses],
        "help_ids": notes,
        "text_height_sp": measurement.text_height_sp,
        "notes_height_sp": measurement.notes_height_sp,
        "page_height_sp": measurement.page_height_sp,
        "usable_height_sp": measurement.usable_height_sp,
        "budget_sp": measurement.budget_sp,
        "chapter_lines": measurement.chapter_lines,
        "groups": groups,
    }


def merge_fragments(verses: list[dict]) -> list[list[dict]]:
    """Rejoin adjacent parts of a source verse when a page boundary moves."""
    result = []
    for verse in verses:
        if result and result[-1]["reference"] == verse["reference"]:
            previous = result[-1]
            start = previous.get("token_start", 0)
            end = start + len(previous["tokens"])
            if verse.get("token_start", 0) != end:
                raise ReaderError("Cannot join noncontiguous source verse fragments")
            result[-1] = {
                **previous,
                "tokens": previous["tokens"] + verse["tokens"],
                "token_start": start,
                "token_end": end + len(verse["tokens"]),
            }
        else:
            result.append(verse)
    return [[verse] for verse in result]


def page_cuts(groups: list) -> list[tuple[list[dict], list[dict]]]:
    verses = [verse for group in groups for verse in group]
    cuts = []
    for index in range(max(0, len(verses) - 3), len(verses)):
        verse = verses[index]
        if index:
            cuts.append((verses[:index], verses[index:]))
        for point in split_points(verse):
            head, tail = split_verse(verse, point)
            cuts.append((verses[:index] + [head], [tail] + verses[index + 1 :]))
    return cuts[-40:]


def balance_three_pages(document: ReaderDocument, compiler: Compiler, plans: list):
    """Try a bounded set of two-boundary moves when one move is insufficient."""
    first, middle, last = plans
    gaps = [plan["usable_height_sp"] - plan["page_height_sp"] for plan in plans]
    best_score = (max(gaps), sum(gaps), 0)
    ceiling = best_score[0] - 65536
    first_cuts, last_cuts = page_cuts(first["groups"]), page_cuts(middle["groups"])
    if not first_cuts or not last_cuts:
        return plans
    first_groups = [merge_fragments(head) for head, _ in first_cuts]
    last_verses = [verse for group in last["groups"] for verse in group]
    last_groups = [merge_fragments(tail + last_verses) for _, tail in last_cuts]
    first_metrics = measure_candidates(compiler, first_groups, document, first["folio"])
    last_metrics = measure_candidates(compiler, last_groups, document, last["folio"])

    def options(metrics):
        legal = [
            index
            for index, metric in enumerate(metrics)
            if metric.fits
            and metric.chapter_lines != 1
            and metric.usable_height_sp - metric.page_height_sp <= ceiling
        ]
        # Keep representative cuts across the feasible range, at most eight.
        if len(legal) > 8:
            return [legal[round(i * (len(legal) - 1) / 7)] for i in range(8)]
        return legal

    pairs = [(left, right) for left in options(first_metrics) for right in options(last_metrics)]
    if not pairs:
        return plans
    middle_groups = [merge_fragments(first_cuts[left][1] + last_cuts[right][0]) for left, right in pairs]
    middle_metrics = []
    for start in range(0, len(pairs), 32):
        middle_metrics.extend(
            measure_candidates(compiler, middle_groups[start : start + 32], document, middle["folio"])
        )
    chosen = None
    for index, (left, right) in enumerate(pairs):
        metric = middle_metrics[index]
        if not metric.fits or metric.chapter_lines == 1:
            continue
        candidate_gaps = [
            value.usable_height_sp - value.page_height_sp
            for value in (first_metrics[left], metric, last_metrics[right])
        ]
        moved = sum(len(verse["tokens"]) for verse in first_cuts[left][1] + last_cuts[right][1])
        score = (max(candidate_gaps), sum(candidate_gaps), moved)
        if score < best_score:
            best_score, chosen = score, index
    if chosen is None or max(gaps) - best_score[0] < 65536:
        return plans
    left, right = pairs[chosen]
    return [
        page_plan(first_groups[left], document, first_metrics[left], first["page"], first["folio"]),
        page_plan(middle_groups[chosen], document, middle_metrics[chosen], middle["page"], middle["folio"]),
        page_plan(last_groups[right], document, last_metrics[right], last["page"], last["folio"]),
    ]


def rebalance_pages(document: ReaderDocument, compiler: Compiler, plans: list, progress=lambda _: None):
    """Reduce chapter-end gaps by moving a bounded amount of preceding text."""
    layout = document.config["layout"]
    if layout.get("verse_layout", "continuous") != "continuous":
        return plans
    result = list(plans)
    threshold = layout["leading_pt"] * 1.25 * 65536
    for index in range(1, len(result) - 1):
        if compiler.cancelled():
            raise Cancelled("Build cancelled")
        previous, current, following = result[index - 1 : index + 2]
        current_gap = current["usable_height_sp"] - current["page_height_sp"]
        if (
            current_gap <= threshold
            or current["groups"][-1][-1]["chapter"] == following["groups"][0][0]["chapter"]
        ):
            continue
        progress(f"Balancing chapter end on page {current['page']}")
        after = [verse for group in current["groups"] for verse in group]
        # Search at most 40 legal cuts in the preceding page's last three verses.
        cuts = page_cuts(previous["groups"])
        if not cuts:
            continue
        left = [merge_fragments(head) for head, _ in cuts]
        right = [merge_fragments(tail + after) for _, tail in cuts]
        left_metrics = measure_candidates(compiler, left, document, previous["folio"])
        right_metrics = measure_candidates(compiler, right, document, current["folio"])
        previous_gap = previous["usable_height_sp"] - previous["page_height_sp"]
        best_score = (max(previous_gap, current_gap), previous_gap + current_gap, 0)
        chosen = None
        for candidate, (first, second) in enumerate(zip(left_metrics, right_metrics, strict=True)):
            if not first.fits or not second.fits or first.chapter_lines == 1 or second.chapter_lines == 1:
                continue
            gaps = (
                first.usable_height_sp - first.page_height_sp,
                second.usable_height_sp - second.page_height_sp,
            )
            moved = sum(len(verse["tokens"]) for verse in cuts[candidate][1])
            score = (max(gaps), sum(gaps), moved)
            if score < best_score:
                best_score, chosen = score, candidate
        # Avoid changing boundaries for an imperceptible improvement.
        if chosen is not None and max(previous_gap, current_gap) - best_score[0] >= 65536:
            result[index - 1] = page_plan(
                left[chosen], document, left_metrics[chosen], previous["page"], previous["folio"]
            )
            result[index] = page_plan(
                right[chosen], document, right_metrics[chosen], current["page"], current["folio"]
            )
        if index >= 2 and best_score[0] > threshold:
            result[index - 2 : index + 1] = balance_three_pages(
                document, compiler, result[index - 2 : index + 1]
            )
    return result


def paginate(document: ReaderDocument, compiler: Compiler, progress=lambda _: None):
    layout = document.config["layout"]
    _, height, margin = paper_dimensions(layout)
    usable_pt = (height - 2 * margin) * PT_PER_MM
    remaining = blocks(document)
    plans = []
    while remaining:
        if compiler.cancelled():
            raise Cancelled("Build cancelled")
        progress(f"Measuring page {len(plans) + 1}")
        folio = layout["first_folio"] + len(plans)
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
            metrics.extend(measure_candidates(compiler, batch, document, folio))
            if not metrics[-1].fits:
                break
        fitting = [i for i, measurement in enumerate(metrics) if measurement.fits]
        consumed = max(fitting) + 1 if fitting else 0
        groups = remaining[:consumed]
        measurement = metrics[consumed - 1] if consumed else None
        # In continuous mode the next verse may start on the current last line.
        # Measure its word prefixes with exactly the helps those words require.
        # An opening can continue after two actual lines beside its badge.
        if layout.get("verse_layout", "continuous") == "continuous" and consumed < len(remaining):
            splits = split_group(remaining[consumed])
            partials = [groups + [head] for head, _ in splits]
            partial_metrics = measure_candidates(compiler, partials, document, folio) if partials else []
            partial_fitting = [
                i for i, metric in enumerate(partial_metrics) if metric.fits and metric.chapter_lines != 1
            ]
            if partial_fitting:
                index = max(partial_fitting)
                groups = partials[index]
                measurement = partial_metrics[index]
                remaining = [splits[index][1]] + remaining[consumed + 1 :]
            else:
                remaining = remaining[consumed:]
        else:
            remaining = remaining[consumed:]
        if measurement is None:
            raise ReaderError(
                f"Layout overflow at {remaining[0][0]['reference']}: a verse/opening and its notes cannot fit. Increase page size or shorten reviewed glosses."
            )
        plans.append(page_plan(groups, document, measurement, len(plans) + 1, folio))
    return rebalance_pages(document, compiler, plans, progress)


def lexicon_tex(document: ReaderDocument, reader_pages: int) -> str:
    layout = document.config["layout"]
    book = catalog()["books"][document.config["book"]]
    headword_command = "ReaderGreek" if document_language(document) == "grc" else "texthebrew"
    english_pt = layout["notes_pt"] * 0.5
    headword_pt = layout["notes_pt"]
    body = [
        r"\begingroup\setLTR\pagestyle{plain}",
        rf"\setcounter{{page}}{{{layout['first_folio'] + reader_pages}}}",
        r"\hypertarget{reader-lexicon}{}\noindent{\large\bfseries "
        + escape_latex(book["title"])
        + rf" — Lexicon}}\hfill\{headword_command}{{"
        + escape_latex(book.get("hebrew") or book.get("edition", ""))
        + r"}\par\smallskip",
    ]
    subtitle = escape_latex(document.config["passage"])
    if document.config["selection"] == "book-frequency":
        subtitle += r"\quad Maximum occurrences in the whole book: " + str(document.config["frequency_max"])
    body.append(r"{\fontsize{7}{9}\selectfont " + subtitle + r"\par}")
    body.extend(
        [
            # The English gloss and stem label share the existing stem-label
            # size. TeX's line boxes reserve the larger Hebrew glyphs' full height.
            rf"\fontsize{{{english_pt}}}{{{english_pt * 1.3}}}\selectfont",
            r"\setlength{\columnsep}{3mm}\setlength{\multicolsep}{5pt}",
            r"\setlength{\parskip}{0pt}\setlength{\lineskip}{0.5pt}",
            r"\raggedright\emergencystretch=1em\raggedcolumns\LTRmulticolcolumns",
            r"\newlength{\LexiconWordWidth}\newsavebox{\LexiconWordBox}",
            r"\newcommand{\LexiconEntry}[4]{\par\begingroup",
            r"\hangindent=\dimexpr\LexiconWordWidth+1mm\relax\hangafter=1",
            r"\noindent\hypertarget{lexicon-entry-#1}{}%",
            rf"\sbox{{\LexiconWordBox}}{{\{headword_command}{{\fontsize{{{headword_pt}}}{{{headword_pt * 1.2}}}\selectfont #2}}}}%",
            r"\makebox[\LexiconWordWidth][l]{\ifdim\wd\LexiconWordBox>\LexiconWordWidth",
            r"\resizebox{\LexiconWordWidth}{!}{\usebox{\LexiconWordBox}}\else\usebox{\LexiconWordBox}\fi}%",
            r"\nobreak\hspace{1mm}#3#4\par\endgroup}",
        ]
    )
    if document.lexicon_appendix:
        body.append(r"\begin{multicols}{4}")
        body.append(r"\setlength{\LexiconWordWidth}{0.4\linewidth}")
        for entry in document.lexicon_appendix:
            stem = escape_latex(entry["stem"].upper()) + r"\enspace " if entry["stem"] else ""
            headword = "".join(c for c in entry["headword"] if not ("\u0591" <= c <= "\u05af"))
            body.append(
                rf"\LexiconEntry{{{entry['id']}}}"
                + "{"
                + escape_latex(headword)
                + "}"
                + "{"
                + stem
                + "}"
                + "{"
                + escape_latex(entry["gloss"].rstrip(". "))
                + ".}"
            )
        body.append(r"\end{multicols}")
    else:
        body.append(r"\bigskip No lexical helps selected for this passage.\par")
    body.append(r"\clearpage\endgroup")
    return "\n".join(body)


def final_tex(document: ReaderDocument, plans: list):
    only = document.config.get("lexicon_only", False)
    appendix_enabled = document.config.get("lexicon_appendix", False) or only
    body = [
        preamble(
            document.config["layout"], lexicon_appendix=appendix_enabled, language=document_language(document)
        )
    ]
    reader_plans = [] if only else plans
    for plan in reader_plans:
        boxes, page = page_tex(plan["groups"], document, f"p{plan['page']}", plan["folio"])
        body.append(boxes)
        body.append(r"\noindent\vbox to\textheight{\hsize=\linewidth")
        body.append(page)
        body.append(r"}\par\newpage")
    if appendix_enabled:
        body.append(lexicon_tex(document, len(reader_plans)))
    body.append(
        r"\raggedright\emergencystretch=3em\section*{Sources and edition}\hypertarget{reader-credits}{}"
    )
    body.append(escape_latex(document.config["name"]) + r"\par\bigskip")
    if document_language(document) == "grc":
        body.append(r"\fontsize{7}{9}\selectfont")
    for notice in document.sources["attributions"] + document.sources["transformations"] + document.warnings:
        body.append(escape_latex(notice) + r"\par\medskip")
    body.append(
        "Text revision: "
        + escape_latex(document.sources.get("text_revision", document.sources.get("oshb_revision", "")))
        + r"\par"
    )
    body.append(
        "Lexicon revision: "
        + escape_latex(document.sources["lexicon"].get("revision", document.sources.get("step_revision", "")))
        + r"\par"
    )
    body.append(r"\end{document}")
    return "\n".join(body)


def verify_pdf(path: Path, plans: list, document: ReaderDocument, log: str):
    pdf = PdfReader(path)
    credits = pdf.named_destinations.get("reader-credits")
    credits_page = pdf.get_destination_page_number(credits) if credits else -1
    only = document.config.get("lexicon_only", False)
    appendix_enabled = document.config.get("lexicon_appendix", False) or only
    if only and plans:
        raise ReaderError("A lexicon-only build cannot contain scripture page plans")
    appendix_pages = credits_page - len(plans) if appendix_enabled else 0
    if (
        credits_page != len(pdf.pages) - 1
        or (appendix_enabled and appendix_pages < 1)
        or (not appendix_enabled and len(pdf.pages) != len(plans) + 1)
    ):
        raise ReaderError(
            f"Unexpected PDF pagination: {len(pdf.pages)} pages, expected {len(plans)} reader pages, "
            "the selected lexicon appendix, and one final credits page"
        )
    expected_entries = {f"lexicon-entry-{entry['id']}" for entry in document.lexicon_appendix}
    actual_entries = {name for name in pdf.named_destinations if name.startswith("lexicon-entry-")}
    if actual_entries != expected_entries:
        raise ReaderError("Compiled PDF lexicon entries do not match the selected lexical helps")
    if appendix_enabled:
        start = pdf.named_destinations.get("reader-lexicon")
        if start is None or pdf.get_destination_page_number(start) != len(plans):
            raise ReaderError("The lexicon appendix must follow the reader pages")
        if any(
            not len(plans) <= pdf.get_destination_page_number(pdf.named_destinations[name]) < credits_page
            for name in expected_entries
        ):
            raise ReaderError("A compiled lexicon entry falls outside the appendix")
    if re.search(r"Overfull \\[hv]box", log):
        raise ReaderError("The PDF has overflowing content; inspect reader.log and adjust the layout.")
    expected = [v["reference"] for v in document.verses]
    actual = []
    reconstructed = []
    for plan in plans:
        fragments = [verse for group in plan["groups"] for verse in group]
        if [verse["reference"] for verse in fragments] != plan["references"]:
            raise ReaderError("Page references do not match their scripture fragments")
        for verse in fragments:
            if actual and actual[-1] == verse["reference"]:
                reconstructed[-1].extend(verse["tokens"])
            else:
                actual.append(verse["reference"])
                reconstructed.append(list(verse["tokens"]))
    if not only and actual != expected:
        raise ReaderError("Page plan lost or duplicated verses")
    if not only and reconstructed != [verse["tokens"] for verse in document.verses]:
        raise ReaderError("Page plan lost, duplicated, or reordered source tokens")
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
    for page in pdf.pages:
        for font in page["/Resources"].get("/Font", {}).values():
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
        "appendix_pages": appendix_pages,
        "appendix_entries": len(document.lexicon_appendix),
        "lexicon_only": only,
        "total_pages": len(pdf.pages),
        "verse_count": len(expected),
        "help_count": len(document.helps),
        "page_membership": "verified",
        "pdf_marker_destinations": "verified",
        "fonts_embedded": True,
    }
