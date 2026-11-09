"""freshness.py on temporary repositories with a local bare remote; nothing outside the temp folder."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import freshness as fr

ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
           GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=ENV).stdout.strip()


def snapshot(root):
    """Working tree content plus HEAD and local branch refs (fetch may only touch remote refs)."""
    files = {p.relative_to(root).as_posix(): p.read_bytes() for p in Path(root).rglob("*")
             if p.is_file() and ".git" not in p.relative_to(root).parts}
    return files, git(root, "rev-parse", "HEAD"), git(root, "for-each-ref", "refs/heads")


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.remote, self.repo = self.root / "origin.git", self.root / "app"
        git(self.root, "init", "-q", "--bare", str(self.remote))
        git(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        git(self.root, "clone", "-q", str(self.remote), str(self.repo))
        git(self.repo, "checkout", "-q", "-B", "main")
        self.commit(self.repo, "base.txt", "base")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        git(self.repo, "fetch", "-q", "origin")
        patcher = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def commit(self, where, name, text):
        (Path(where) / name).write_text(text)
        git(where, "add", name)
        git(where, "commit", "-q", "-m", name)

    def upstream_commit(self, name="up.txt", branch="main"):
        other = self.root / ("other-" + name)
        git(self.root, "clone", "-q", str(self.remote), str(other))
        git(other, "checkout", "-q", "-B", branch)
        self.commit(other, name, "up")
        git(other, "push", "-q", "origin", branch)

    def age(self, days):
        old = time.time() - days * 86400
        os.utime(self.repo / ".git/FETCH_HEAD", (old, old))

    def test_fresh_clone(self):
        state = fr.repo_state(self.repo)
        self.assertFalse(state["stale"], state["reasons"])
        self.assertEqual((state["branch"], state["defaultBranch"], state["base"]), ("main", "main", "origin/main"))
        self.assertEqual((state["ahead"], state["behind"], state["dirty"], state["ffSafe"]), (0, 0, 0, False))

    def test_old_or_missing_fetch_is_stale(self):
        self.age(3)
        state = fr.repo_state(self.repo)
        self.assertTrue(state["stale"])
        self.assertIn("days ago", state["reasons"][0])
        self.assertFalse(fr.repo_state(self.repo, max_age_days=5)["stale"])
        os.remove(self.repo / ".git/FETCH_HEAD")
        self.assertIn("never fetched (no FETCH_HEAD)", fr.repo_state(self.repo)["reasons"])

    def test_stale_refs_hide_remote_work_until_fetch(self):
        self.upstream_commit()
        before = fr.repo_state(self.repo)
        self.assertEqual(before["behind"], 0)  # local refs say "up to date": not evidence
        self.age(5)
        tree = snapshot(self.repo)
        after = fr.repo_state(self.repo, fetch=True)
        self.assertTrue(after["fetched"])
        self.assertEqual(after["behind"], 1)
        self.assertTrue(after["stale"] and after["ffSafe"])
        self.assertLess(after["fetchedDaysAgo"], 1)
        self.assertEqual(snapshot(self.repo), tree)  # fetch only: no pull, merge or fast-forward
        self.assertFalse((self.repo / "up.txt").exists())

    def test_fast_forward_only_when_clean_on_default_branch(self):
        self.upstream_commit()
        git(self.repo, "fetch", "-q", "origin")
        self.assertTrue(fr.repo_state(self.repo)["ffSafe"])
        (self.repo / "base.txt").write_text("local edit")
        state = fr.repo_state(self.repo)
        self.assertEqual((state["dirty"], state["ffSafe"]), (1, False))
        git(self.repo, "checkout", "-q", "--", "base.txt")
        git(self.repo, "checkout", "-q", "-b", "feature", "--track", "origin/main")
        self.assertFalse(fr.repo_state(self.repo)["ffSafe"])  # behind, but not on the default branch
        git(self.repo, "checkout", "-q", "main")
        self.commit(self.repo, "mine.txt", "mine")
        state = fr.repo_state(self.repo)
        self.assertEqual((state["ahead"], state["behind"], state["ffSafe"]), (1, 1, False))  # diverged

    def test_prune_and_failed_fetch(self):
        git(self.repo, "push", "-q", "origin", "main:gone")
        git(self.repo, "fetch", "-q", "origin")
        git(self.remote, "branch", "-D", "gone")
        fr.repo_state(self.repo, fetch=True)
        self.assertEqual(git(self.repo, "branch", "-r", "--list", "origin/gone"), "")  # --prune
        git(self.repo, "remote", "set-url", "origin", str(self.root / "missing.git"))
        state = fr.repo_state(self.repo, fetch=True)
        self.assertFalse(state["fetched"])
        self.assertTrue(state["stale"])
        self.assertTrue(any("fetch failed" in r for r in state["reasons"]))

    def test_branch_upstream_and_explicit_base(self):
        git(self.repo, "checkout", "-q", "-b", "topic")
        git(self.repo, "push", "-q", "-u", "origin", "topic")
        self.upstream_commit("t.txt", branch="topic")
        git(self.repo, "fetch", "-q", "origin")
        state = fr.repo_state(self.repo)
        self.assertEqual((state["base"], state["behind"]), ("origin/topic", 1))
        self.assertEqual(fr.repo_state(self.repo, base="origin/main")["behind"], 0)

    def test_cli_exit_codes_and_json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fr.main([str(self.repo), "--json"]), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data[0]["repo"], "app")
        self.assertNotIn("dirtyLines", data[0])
        self.age(9)
        with contextlib.redirect_stdout(io.StringIO()) as text:
            self.assertEqual(fr.main([str(self.repo), str(self.root / "nope")]), 1)
        self.assertIn("STALE", text.getvalue())
        self.assertIn("not a git checkout", text.getvalue())


if __name__ == "__main__":
    unittest.main()
