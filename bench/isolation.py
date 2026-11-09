"""Run grading inside bubblewrap, away from the host.

The agent controls every file in a task workspace (scripts, tests, modules, symlinks, even
`.git/config` hooks and diff drivers). bench.py therefore runs the whole grader
(grade_worker.py) through `run()`: a fresh bubblewrap sandbox with a read-only root, no network, a private /tmp, /run and
/home, no inherited environment, and write access only to the explicit workspace and scratch roots. Without bubblewrap, grading refuses unless unsafe grading was chosen
explicitly (`bench.py --unsafe-grading`). Standard library only.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys

CompletedProcess = subprocess.CompletedProcess
TimeoutExpired = subprocess.TimeoutExpired
CalledProcessError = subprocess.CalledProcessError
PIPE = subprocess.PIPE
DEVNULL = subprocess.DEVNULL
STDOUT = subprocess.STDOUT

UNSAFE = False   # set by bench.py --unsafe-grading; never the default
HIDDEN = ("/tmp", "/var/tmp", "/run", "/home", "/root", "/mnt", "/media", "/srv")
KEEP_ENV = ("LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ")


class IsolationUnavailable(RuntimeError):
    pass


def available():
    return bool(shutil.which("bwrap")) and sys.platform.startswith("linux")


class UnsafeBinds(ValueError):
    """A writable root overlaps a path that must stay read-only."""


def check_binds(roots, read_only=(), protect=()):
    """Refuse writable ROOTS that equal, contain or lie inside a READ_ONLY path, or contain a PROTECTED one."""
    roots = [Path(r).resolve() for r in roots]
    for root in roots:
        for path in (Path(p).resolve() for p in read_only):
            if root == path or path in root.parents or root in path.parents:
                raise UnsafeBinds(f"writable {root} overlaps read-only {path}; refusing to run")
        for path in (Path(p).resolve() for p in protect):
            if root == path or root in path.parents:
                raise UnsafeBinds(f"writable {root} contains {path}; refusing to run")
    return roots


def command(cmd, cwd, binds, env=None, home=None, read_only=()):
    """The bubblewrap argv for CMD with write access only to BINDS."""
    bwrap = shutil.which("bwrap")
    args = [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
    home = Path.home().resolve()
    for hidden in (*HIDDEN, str(home)):
        if os.path.isdir(hidden) and not os.path.islink(hidden):
            args += ["--tmpfs", hidden]
    python = set()
    for path in (Path(sys.base_prefix), Path(sys.prefix), Path(sys.executable).parent):
        python |= {Path(os.path.abspath(path)), path.resolve()}  # both the linked and the real location
    # Writable binds first, read-only binds last: a later mount wins, so read-only always prevails.
    for path in sorted(binds):
        if path.exists():
            args += ["--bind", str(path), str(path)]
    for path in sorted(python):  # the grader's interpreter may live under a hidden folder (for example uv)
        if any(path == Path(h) or Path(h) in path.parents for h in (*HIDDEN, str(home))):
            args += ["--ro-bind", str(path), str(path)]
    for path in sorted(Path(p).resolve() for p in read_only):
        if path.exists():
            args += ["--ro-bind", str(path), str(path)]
    args += ["--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
             "--setenv", "PATH", os.pathsep.join([str(Path(sys.executable).parent), "/usr/local/bin", "/usr/bin", "/bin"]),
             "--setenv", "HOME", str(home or cwd or "/"),
             "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
             "--setenv", "GIT_CONFIG_NOSYSTEM", "1"]
    for key in KEEP_ENV:
        if os.environ.get(key):
            args += ["--setenv", key, os.environ[key]]
    for key, value in (env or {}).items():
        if key.startswith("GIT_") and key not in ("GIT_CONFIG_GLOBAL",) and value is not None:
            args += ["--setenv", key, str(value)]
    if cwd:
        args += ["--chdir", str(cwd)]
    return args + ["--", *map(str, cmd)]


def run(cmd, *args, cwd=None, env=None, roots=(), read_only=(), protect=(), check=False, **kwargs):
    """subprocess.run() replacement: same result object, executed inside the sandbox.

    Only the explicit ROOTS are writable (never anything inferred from the command); READ_ONLY
    paths are mounted read-only on top; PROTECT paths must not lie inside a writable root.
    """
    if args:
        raise TypeError("isolation.run takes the command and keyword arguments only")
    cmd = [cmd] if isinstance(cmd, (str, os.PathLike)) and not kwargs.get("shell") else list(cmd)
    if kwargs.pop("shell", False):
        cmd = ["/bin/sh", "-c", " ".join(map(str, cmd))]
    if UNSAFE:
        check_binds(roots, read_only, protect)
        return subprocess.run(cmd, cwd=cwd, env=env, check=check, **kwargs)
    if not available():
        raise IsolationUnavailable("bubblewrap (bwrap) is required to grade agent-written code; "
                                   "install it or pass --unsafe-grading to run graders unsandboxed")
    binds = set(check_binds(roots, read_only, protect))
    home = Path(roots[0]).resolve() if roots else None
    result = subprocess.run(command(cmd, cwd and Path(cwd).resolve(), binds, env, home, read_only), check=False, **kwargs)
    result.args = cmd
    if check and result.returncode:
        raise CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result
