"""./ra template — official journal LaTeX template handling.

  fetch <url|ctan:NAME> [--name NAME]   download a template (zip or single file) into templates/NAME/
                                        ctan:elsarticle -> https://mirrors.ctan.org/macros/latex/contrib/elsarticle.zip
  list                                  downloaded templates and their sources
  install NAME [--force]                copy class/style files (.cls .bst .sty .bbx .cbx .clo .cfg) into paper/
                                        (the example .tex stays in templates/NAME/ as the reference to follow)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import re
import shutil
import sys
import urllib.parse
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
from ra import core, net, pipeline  # noqa: E402

SUPPORT_EXT = {".cls", ".bst", ".sty", ".bbx", ".cbx", ".clo", ".cfg", ".def"}
MAX_BYTES = 60 * 1024 * 1024


def fetch(url: str, name: str | None) -> int:
    if url.startswith("ctan:"):
        pkg = url[5:]
        url = f"https://mirrors.ctan.org/macros/latex/contrib/{pkg}.zip"
        name = name or pkg
    if not re.match(r"^https?://", url):
        print("only http(s) URLs or ctan:NAME are supported", file=sys.stderr)
        return 2
    base = Path(urllib.parse.urlparse(url).path).name or "template"
    name = name or re.sub(r"\.(zip|tex|cls)$", "", base, flags=re.I)
    try:
        data = net.get(url, binary=True, timeout=120, retries=2)
    except net.HTTPError as e:
        print(f"download failed: {e}", file=sys.stderr)
        return 1
    if len(data) > MAX_BYTES:
        print("refusing: file larger than 60 MB", file=sys.stderr)
        return 1
    head = data[:512].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        print("the URL returned an HTML page, not a template file. Find the direct download link (usually a .zip) "
              "or use ctan:<classname> if the class is on CTAN.", file=sys.stderr)
        return 1
    dest = core.path("templates", name)
    dest.mkdir(parents=True, exist_ok=True)
    if data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                target = (dest / info.filename).resolve()
                if not str(target).startswith(str(dest.resolve())) or info.is_dir():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
    else:
        (dest / base).write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    src = core.path("templates", "SOURCES.md")
    if not src.exists():
        core.write_text(src, "# Template sources\n\n| name | url | sha256 | fetched |\n|---|---|---|---|\n")
    core.append_text(src, f"| {name} | {url} | `{sha[:16]}` | {core.now()} |\n")
    files = sorted(core.rel(p) for p in dest.rglob("*") if p.is_file())
    print(f"saved {len(files)} file(s) to templates/{name}/")
    for f in files[:40]:
        print(f"  {f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra template", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("fetch"); s.add_argument("url"); s.add_argument("--name")
    sub.add_parser("list")
    s = sub.add_parser("install"); s.add_argument("name"); s.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if pipeline.intake_missing():
        print("refused: fill in the journal fields of project.json first", file=sys.stderr)
        return 1
    if a.cmd == "fetch":
        return fetch(a.url, a.name)
    if a.cmd == "list":
        print(core.read_text(core.path("templates", "SOURCES.md")) or "no templates downloaded yet")
        return 0
    if a.cmd == "install":
        src = core.path("templates", a.name)
        if not src.is_dir():
            print(f"templates/{a.name} not found", file=sys.stderr)
            return 1
        copied, skipped = [], []
        for p in src.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORT_EXT:
                target = core.path("paper", p.name)
                if target.exists() and target.read_bytes() != p.read_bytes() and not a.force:
                    skipped.append(p.name)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, target)
                copied.append(p.name)
        print(f"installed into paper/: {', '.join(sorted(copied)) or '(nothing)'}")
        if skipped:
            print(f"skipped (differs, use --force): {', '.join(skipped)}")
        examples = sorted(core.rel(p) for p in src.rglob("*.tex"))
        print("reference .tex files to follow when restructuring paper/main.tex:\n  " + "\n  ".join(examples[:15]))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
