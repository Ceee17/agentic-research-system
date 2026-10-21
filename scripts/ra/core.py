"""Workspace paths, text/JSON IO, hashing and git helpers.

Layout: the *workspace* (the folder holding `ra`, `.claude/`, `scripts/`, `CLAUDE.md`) is shared
by all papers; each paper lives in `papers/<slug>/` with its own state, files and git repository.
`root()` / `path()` / `rel()` refer to the ACTIVE paper; `ws()` / `wpath()` / `wrel()` to the
workspace. The active paper is chosen by the human (`PAPER <slug>` in chat, `./ra paper use`).

Everything here is standard-library only so hooks and checks run before any
virtualenv exists.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class NoActivePaper(RuntimeError):
    pass


# --------------------------------------------------------------------- paths
def ws() -> Path:
    """Workspace root: the directory that holds the `ra` launcher."""
    env = os.environ.get("RA_WORKSPACE")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[2]


def wpath(*parts: str) -> Path:
    return ws().joinpath(*parts)


def papers_dir() -> Path:
    return ws() / "papers"


def list_papers() -> list[str]:
    d = papers_dir()
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and (p / "state.json").exists())


def active_paper() -> str | None:
    """Slug of the active paper (env RA_PAPER for human terminal use, else .ra/active-paper)."""
    slug = (os.environ.get("RA_PAPER") or read_text(wpath(".ra", "active-paper")) or "").strip()
    return slug if slug and SLUG_RE.match(slug) and (papers_dir() / slug / "state.json").exists() else None


def set_active_paper(slug: str | None) -> None:
    p = wpath(".ra", "active-paper")
    if slug:
        write_text(p, slug + "\n")
    elif p.exists():
        p.unlink()


def no_paper_message() -> str:
    papers = list_papers()
    have = f"existing papers: {', '.join(papers)}; " if papers else "no papers yet; "
    return ("No active paper. The human chooses one by typing `PAPER <name>` in chat (" + have +
            "a new one with `NEW PAPER <name>`), or `./ra paper use <name>` in a terminal.")


def root() -> Path:
    """Root of the ACTIVE paper (papers/<slug>/)."""
    slug = active_paper()
    if not slug:
        raise NoActivePaper(no_paper_message())
    return papers_dir() / slug


def path(*parts: str) -> Path:
    return root().joinpath(*parts)


def _rel_to(base: Path, p) -> str | None:
    b = os.path.abspath(str(base))
    s = str(p)
    target = os.path.abspath(s if os.path.isabs(s) else os.path.join(b, s))
    nb, nt = os.path.normcase(b), os.path.normcase(target)
    if nt == nb:
        return ""
    prefix = nb.rstrip("\\/") + os.sep
    if not nt.startswith(prefix):
        return None
    return target[len(prefix):].replace(os.sep, "/")


def rel(p) -> str | None:
    """Path relative to the active paper root (relative input = paper-relative); None if outside
    the paper or when no paper is active."""
    try:
        return _rel_to(root(), p)
    except NoActivePaper:
        return None


def wrel(p) -> str | None:
    """Workspace-relative POSIX path (relative input = workspace-relative); None if outside."""
    return _rel_to(ws(), p)


def paper_of(p) -> str | None:
    """Slug of the paper folder that contains `p` (workspace-relative or absolute), if any."""
    r = wrel(p)
    if r and r.startswith("papers/"):
        parts = r.split("/")
        return parts[1] if len(parts) > 1 and parts[1] else None
    return None


def resolve_arg(p: str) -> Path:
    """A path given on a `./ra` command line: absolute, `papers/<active>/...`, or paper-relative."""
    if os.path.isabs(p):
        return Path(p)
    norm = p.replace("\\", "/")
    slug = active_paper()
    if slug and norm.startswith(f"papers/{slug}/"):
        return wpath(norm)
    return path(norm)


# ------------------------------------------------------------------ time / io
def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return _dt.date.today().isoformat()


def stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def read_text(p) -> str | None:
    """Read UTF-8 text with universal newlines; None if the file does not exist."""
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def write_text(p, text: str) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def append_text(p, text: str) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_json(p, default=None):
    text = read_text(p)
    if text is None or not text.strip():
        return default
    return json.loads(text)


def write_json(p, data) -> None:
    """Atomic JSON write (temp file + replace), retrying briefly on Windows file locks."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    for attempt in range(5):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            if attempt == 4:
                os.unlink(tmp)
                raise
            time.sleep(0.2)


def norm_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(norm_newlines(text).encode("utf-8")).hexdigest()


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def short_hash(text: str, n: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


# ----------------------------------------------------------------------- git
def is_git_repo() -> bool:
    """The active paper has its own git repository (papers/<slug>/.git)."""
    try:
        return (root() / ".git").exists() and shutil.which("git") is not None
    except NoActivePaper:
        return False


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(root()), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=check,
    )


def git_head_file(relpath: str) -> str | None:
    """Content of `relpath` at HEAD, or None (no repo / untracked / no commits)."""
    if not is_git_repo():
        return None
    r = git("show", f"HEAD:{relpath}")
    return norm_newlines(r.stdout) if r.returncode == 0 else None


def git_head() -> str | None:
    if not is_git_repo():
        return None
    r = git("rev-parse", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else None


def git_commit_all(message: str) -> str | None:
    """Stage everything and commit. Returns the new HEAD, or None if nothing was committed."""
    if not is_git_repo():
        print("note: this paper has no git repository; skipping commit", file=sys.stderr)
        return None
    git("add", "-A")
    r = git("commit", "-m", message)
    if r.returncode != 0:
        out = (r.stdout + r.stderr).strip()
        if "nothing to commit" in out or "no changes added" in out:
            return None
        print(f"warning: git commit failed: {out[-400:]}", file=sys.stderr)
        return None
    return git_head()


# ---------------------------------------------------------------------- misc
def in_agent_session() -> bool:
    """True when running inside a Claude Code tool call (Claude Code sets CLAUDECODE=1)."""
    return os.environ.get("CLAUDECODE") == "1"


def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    sys.exit(code)
