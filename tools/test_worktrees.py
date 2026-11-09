"""worktrees.py on temporary repositories with a local bare remote; nothing outside the temp folder."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("worktrees.py")
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
           GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=ENV).stdout.strip()


class WorktreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.remote, self.repo = self.root / "origin.git", self.root / "app"
        git(self.root, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(self.root, "init", "-q", "-b", "main", str(self.repo))
        git(self.repo, "remote", "add", "origin", str(self.remote))
        self.commit(self.repo, "base.txt", "base")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")

    def commit(self, where, name, text):
        (Path(where) / name).write_text(text)
        git(where, "add", name)
        git(where, "commit", "-q", "-m", name)

    def add(self, name, branch):
        path = self.root / name
        git(self.repo, "worktree", "add", "-q", "-b", branch, str(path), "main")
        return path

    def merge(self, branch, push=True):
        git(self.repo, "merge", "-q", "--no-ff", "-m", "merge " + branch, branch)
        if push:
            git(self.repo, "push", "-q", "origin", "main", branch)

    def run_tool(self, *args):
        out = subprocess.run([sys.executable, str(SCRIPT), str(self.repo), "--json", *args],
                             capture_output=True, text=True, env=ENV)
        self.assertIn(out.returncode, (0,), out.stderr)
        return {Path(i["path"]).name: i for i in json.loads(out.stdout)[0]["worktrees"]}, json.loads(out.stdout)[0]

    def fixture(self):
        loose = self.add("scratch-wt", "experiment")  # before the unpushed merge below, so it holds only pushed commits
        done = self.add("app-wt-tkt42-done", "tkt-42/done")
        self.commit(done, "done.txt", "done")
        self.merge("tkt-42/done")
        dirty = self.add("app-wt-tkt42-dirty", "tkt-42/dirty")
        self.commit(dirty, "dirty.txt", "dirty")
        self.merge("tkt-42/dirty")
        (dirty / "scratch.txt").write_text("untracked work")
        open_wt = self.add("app-wt-tkt43-open", "tkt-43/open")
        self.commit(open_wt, "open.txt", "open")
        git(self.repo, "push", "-q", "origin", "tkt-43/open")
        local = self.add("app-wt-tkt44-local", "tkt-44/local")
        self.commit(local, "local.txt", "local")
        self.merge("tkt-44/local", push=False)  # merged into local main, but never pushed anywhere
        return done, dirty, open_wt, local, loose

    def test_dry_run_reports_by_ticket_and_marks_only_merged_clean_pushed(self):
        done, dirty, open_wt, local, loose = self.fixture()
        items, report = self.run_tool()
        self.assertEqual(report["base"], "refs/remotes/origin/main")
        self.assertEqual(sorted(report["tickets"]), ["TKT-42", "TKT-43", "TKT-44", "unticketed"])
        self.assertEqual(len(report["tickets"]["TKT-42"]), 2)
        removable = sorted(name for name, item in items.items() if item["removable"])
        self.assertEqual(removable, ["app-wt-tkt42-done", "scratch-wt"])  # unchanged branch on main is merged, clean, pushed
        self.assertIn("1 untracked files", items[dirty.name]["keep_reasons"])
        self.assertTrue(any(r.startswith("not merged") for r in items[open_wt.name]["keep_reasons"]))
        self.assertIn("1 commits on no remote", items[local.name]["keep_reasons"])
        self.assertIn("main worktree", items["app"]["keep_reasons"])
        for path in (done, dirty, open_wt, local, loose):
            self.assertTrue(path.is_dir())  # dry run removes nothing

    def test_apply_removes_only_removable_and_keeps_branches(self):
        done, dirty, open_wt, local, loose = self.fixture()
        out = subprocess.run([sys.executable, str(SCRIPT), str(self.repo), "--apply"], capture_output=True, text=True, env=ENV)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse(done.exists())
        self.assertFalse(loose.exists())
        for path in (dirty, open_wt, local):
            self.assertTrue(path.is_dir(), path)
        self.assertTrue((dirty / "scratch.txt").is_file())
        self.assertIn("tkt-42/done", git(self.repo, "branch", "--list", "tkt-42/done"))

    def test_ignored_files_block_removal_and_are_reported(self):
        # Reviewer probe: merged, pushed worktree whose only content beyond the branch is ignored data.
        (self.repo / ".gitignore").write_text("local-data/\n.env\n*.sqlite3\n")
        git(self.repo, "add", ".gitignore")
        git(self.repo, "commit", "-q", "-m", "ignore local data")
        git(self.repo, "push", "-q", "origin", "main")
        kept = self.add("app-wt-tkt49-kept", "tkt-49/kept")
        self.commit(kept, "feature.txt", "feature")
        self.merge("tkt-49/kept")
        (kept / "local-data").mkdir()
        (kept / "local-data/keep.txt").write_text("only copy")
        env_wt = self.add("app-wt-tkt50-env", "tkt-50/env")
        self.commit(env_wt, "env.txt", "env")
        self.merge("tkt-50/env")
        (env_wt / ".env").write_text("SETTING=local")
        (env_wt / "app.sqlite3").write_text("db")
        items, _ = self.run_tool("--apply")
        for path, needle in ((kept, "local-data/"), (env_wt, ".env")):
            item = items[path.name]
            self.assertTrue(item["merged"])
            self.assertEqual(item["unpushed"], 0)
            self.assertFalse(item["removable"])
            self.assertTrue(any("ignored files" in r for r in item["keep_reasons"]), item["keep_reasons"])
            self.assertTrue(any(needle in f for f in item["blocking_files"]), item["blocking_files"])
            self.assertTrue(path.is_dir())
        self.assertEqual((kept / "local-data/keep.txt").read_text(), "only copy")
        self.assertTrue((env_wt / ".env").is_file() and (env_wt / "app.sqlite3").is_file())

    def test_locked_and_missing_worktrees_are_kept(self):
        locked = self.add("app-wt-tkt45-locked", "tkt-45/locked")
        git(self.repo, "worktree", "lock", str(locked))
        gone = self.add("app-wt-tkt46-gone", "tkt-46/gone")
        subprocess.run(["rm", "-rf", str(gone)], check=True)
        items, _ = self.run_tool("--apply")
        self.assertIn("locked", items[locked.name]["keep_reasons"])
        self.assertFalse(items[gone.name]["removable"])
        self.assertTrue(locked.is_dir())

    def test_more_than_eight_slices_warns(self):
        for n in range(9):
            self.add(f"app-wt-tkt47-s{n}", f"tkt-47/s{n}")
        _, report = self.run_tool()
        self.assertEqual(len(report["warnings"]), 1)
        self.assertIn("TKT-47: 9 worktrees exceed 8 slices", report["warnings"][0])

    def test_explicit_base_and_duplicate_paths(self):
        done = self.add("app-wt-tkt48-x", "tkt-48/x")
        self.commit(done, "x.txt", "x")
        git(self.repo, "push", "-q", "origin", "tkt-48/x")
        out = subprocess.run([sys.executable, str(SCRIPT), str(self.repo), str(done), "--base", "tkt-48/x", "--json"],
                             capture_output=True, text=True, env=ENV)
        reports = json.loads(out.stdout)
        self.assertEqual(len(reports), 1)  # the worktree path names the same repository
        items = {Path(i["path"]).name: i for i in reports[0]["worktrees"]}
        self.assertTrue(items[done.name]["removable"])


if __name__ == "__main__":
    unittest.main()
