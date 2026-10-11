"""Install a checksum-pinned, project-local XeLaTeX on Linux x86-64; no sudo."""

import argparse
import hashlib
import platform
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "TinyTeX.tar.gz": (
        "https://github.com/rstudio/tinytex-releases/releases/download/v2026.10/TinyTeX-v2026.10.tar.gz",
        "4ac08282f9964cdd9698cb141bc4d9fa3418024f055f3568e573af42ab9d936b",
    ),
    "bidi.tar.xz": (
        "https://texlive.info/tlnet-archive/2026/10/01/tlnet/archive/bidi.tar.xz",
        "eaa01a43b4a21659a65810c2afbebc232c725ac81b01b66b5b5227499444db79",
    ),
}


def acquire(directory, name):
    url, checksum = ASSETS[name]
    archive = directory / name
    if not archive.exists():
        if shutil.which("curl") is None:
            raise RuntimeError("Install curl to download the pinned TeX archives")
        print(f"Downloading {name}", flush=True)
        partial = archive.with_suffix(archive.suffix + ".part")
        try:
            # texlive.info serves a bot challenge to urllib clients. Use curl's
            # normal request, then verify the archive before promoting the download.
            response = subprocess.run(
                [
                    "curl",
                    "--fail",
                    "--location",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "120",
                    "--output",
                    str(partial),
                    "--write-out",
                    "%{content_type}",
                    url,
                ],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )
            if response.stdout.lower().startswith("text/html"):
                raise RuntimeError(
                    f"Download of {name} returned HTML instead of an archive from {url}; "
                    "the host may be serving a bot challenge or error page; not installed"
                )
            actual = hashlib.sha256(partial.read_bytes()).hexdigest()
            if actual != checksum:
                raise RuntimeError(
                    f"Checksum mismatch for {name} from {url}: expected {checksum}, got {actual}; not installed"
                )
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
        raise RuntimeError(f"Cached {name} has the wrong checksum; move it aside and retry")
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / ".tools")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.exit(
            1,
            "Portable setup supports Linux x86-64 (including WSL). Install XeLaTeX separately on other systems.\n",
        )
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    distribution = directory / ".TinyTeX"
    binary = distribution / "bin/x86_64-linux"
    if not (binary / "xelatex").is_file():
        with tarfile.open(acquire(directory, "TinyTeX.tar.gz")) as archive:
            archive.extractall(directory, filter="data")
    if not (distribution / "texmf-dist/tex/latex/bidi/bidi.sty").is_file():
        with tarfile.open(acquire(directory, "bidi.tar.xz")) as archive:
            archive.extractall(distribution / "texmf-dist", filter="data")
        subprocess.run([str(binary / "mktexlsr")], check=True)
    for name in ("fontspec.sty", "xcolor.sty", "polyglossia.sty", "bidi.sty", "hyperref.sty", "geometry.sty"):
        subprocess.run([str(binary / "kpsewhich"), name], check=True)
    print(f"XeLaTeX ready: {binary / 'xelatex'}")


if __name__ == "__main__":
    main()
