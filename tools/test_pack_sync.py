"""pack_sync.py against temporary git repositories; no network and no real checkouts."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name("pack_sync.py")
PACK = "project-packs/sample"
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
               GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
# Built at runtime so this file itself stays clean for the package privacy scan.
PRIVATE_PATH = "/" + "home" + "/someone/private/notes"


def load_module():
    spec = importlib.util.spec_from_file_location("pack_sync", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env=GIT_ENV).stdout


def snapshot(repo):
    """HEAD, refs, status and every working-tree byte of REPO."""
    files = {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(repo.rglob("*")) if p.is_file() and ".git" not in p.relative_to(repo).parts}
    return git(repo, "rev-parse", "HEAD"), git(repo, "status", "--porcelain"), git(repo, "show-ref"), files


class PackSyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.source, self.up, self.root = base / "source", base / "upstream", base / "package"
        self.source.mkdir()
        git(self.source, "init", "-q", "-b", "main")
        self.commit({"Skills/demo/SKILL.md": "# Demo\n\nStep one.\n", "Skills/demo/references/notes.md": "Notes.\n",
                     "Skills/other/SKILL.md": "# Other\n"})
        subprocess.run(["git", "clone", "-q", str(self.source), str(self.up)], check=True, env=GIT_ENV)
        skills = self.root / PACK / "skills"
        (skills / "demo/references").mkdir(parents=True)
        (skills / "demo/SKILL.md").write_text("# Demo\n\nStep one.\n")
        (skills / "demo/references/notes.md").write_text("Notes.\n")
        (skills / "pack-own").mkdir()
        (skills / "pack-own/SKILL.md").write_text("# Pack own\n")
        (self.root / PACK / "publication.json").write_text(json.dumps({"word_hashes": [], "brand_pattern": r"(?!)", "allow_lines": {}}))
        self.config = self.root / PACK / "pack-sync.json"
        self.config.write_text(json.dumps({
            "upstream": {"repository": "example/skills", "ref": "origin/main", "skills_root": "Skills"},
            "pack_root": PACK + "/skills",
            "skills": {"demo": {"upstream": "demo"}},
            "known_candidates": {"other": "reviewed, not adopted"},
        }, indent=2))
        self.before = snapshot(self.up)
        self.assertEqual(self.tool("pull", "demo")[0], 0)  # records the base for the identical files

    def tearDown(self):
        self.assertEqual(snapshot(self.up), self.before, "the upstream checkout must never change")

    def commit(self, files, delete=()):
        for name in delete:
            (self.source / name).unlink()
            if not any((self.source / name).parent.iterdir()):
                (self.source / name).parent.rmdir()
        for name, text in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        git(self.source, "add", "-A")
        git(self.source, "commit", "-q", "-m", "change")

    def advance(self, files, delete=()):
        """Commit upstream and fetch it, leaving the checkout's working tree and HEAD as they were."""
        self.commit(files, delete)
        git(self.up, "fetch", "-q", "origin")
        self.before = snapshot(self.up)

    def tool(self, *args):
        out = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--upstream", str(self.up),
                              "--json", *args], capture_output=True, text=True,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        return out.returncode, (json.loads(out.stdout) if out.stdout.strip() else None), out.stderr

    def actions(self, report, skill="demo"):
        return {f["file"]: f["action"] for s in report["skills"] if s["name"] == skill for f in s["files"]}

    def pack_file(self, name):
        return (self.root / PACK / "skills/demo" / name).read_text()

    def base(self, name):
        return json.loads(self.config.read_text())["skills"]["demo"]["files"][name]

    def test_identical_is_in_sync_and_json_shape(self):
        code, report, _ = self.tool("status")
        self.assertEqual(code, 0)
        self.assertEqual(set(report), {"upstream", "in_sync", "drift", "skills", "candidates", "pack_only_skills"})
        self.assertEqual(set(report["upstream"]), {"ref", "rev"})
        self.assertTrue(report["in_sync"])
        self.assertEqual(report["drift"], [])
        skill = report["skills"][0]
        self.assertEqual(set(skill), {"name", "upstream", "pack", "upstream_present", "pack_present", "counts", "files"})
        self.assertEqual(self.actions(report), {"SKILL.md": "in-sync", "references/notes.md": "in-sync"})
        self.assertEqual(set(skill["files"][0]), {"file", "policy", "state", "change", "action"})
        self.assertEqual(report["candidates"], [{"name": "other", "known": True, "note": "reviewed, not adopted"}])
        self.assertEqual(report["pack_only_skills"], ["pack-own"])
        self.assertEqual(self.base("SKILL.md")["base_rev"], git(self.up, "rev-parse", "origin/main").strip())

    def test_reads_the_fetched_ref_not_the_working_tree(self):
        (self.up / "Skills/demo/SKILL.md").write_text("# Uncommitted local edit\n")
        self.before = snapshot(self.up)
        code, report, _ = self.tool("status")
        self.assertEqual((code, self.actions(report)["SKILL.md"]), (0, "in-sync"))

    def test_fetch_updates_only_refs(self):
        self.commit({"Skills/demo/SKILL.md": "# Demo v2\n"})
        code, report, _ = self.tool_fetch()
        self.assertEqual((code, self.actions(report)["SKILL.md"]), (1, "pull"))
        after = snapshot(self.up)
        self.assertEqual((after[0], after[1], after[3]), (self.before[0], self.before[1], self.before[3]))
        self.before = after

    def tool_fetch(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--upstream", str(self.up),
                              "--fetch", "--json", "status"], capture_output=True, text=True, env=GIT_ENV)
        return out.returncode, json.loads(out.stdout), out.stderr

    def test_upstream_only_change_is_pulled(self):
        self.advance({"Skills/demo/SKILL.md": "# Demo\n\nStep one, improved.\n",
                      "Skills/demo/references/new.md": "New.\n"}, delete=["Skills/demo/references/notes.md"])
        code, report, _ = self.tool("status")
        self.assertEqual(code, 1)
        self.assertEqual(self.actions(report), {"SKILL.md": "pull", "references/new.md": "pull",
                                                "references/notes.md": "pull"})
        code, result, _ = self.tool("pull", "demo")
        self.assertEqual(code, 0)
        self.assertEqual({p["file"]: p["operation"] for p in result["pulled"]},
                         {"SKILL.md": "updated", "references/new.md": "created", "references/notes.md": "deleted"})
        self.assertEqual(self.pack_file("SKILL.md"), "# Demo\n\nStep one, improved.\n")
        self.assertFalse((self.root / PACK / "skills/demo/references/notes.md").exists())
        self.assertEqual(self.base("SKILL.md")["base_rev"], result["upstream"]["rev"])
        self.assertIsNone(self.base("references/notes.md")["base_sha256"])
        self.assertEqual(self.tool("status")[0], 0)

    def test_pull_selected_files_only(self):
        self.advance({"Skills/demo/SKILL.md": "# Demo v2\n", "Skills/demo/references/notes.md": "Notes v2.\n"})
        code, result, _ = self.tool("pull", "demo", "--files", "SKILL.md")
        self.assertEqual(code, 0)
        self.assertEqual(self.pack_file("references/notes.md"), "Notes.\n")
        self.assertEqual(self.actions(self.tool("status")[1])["references/notes.md"], "pull")

    def test_pack_local_change_is_kept(self):
        (self.root / PACK / "skills/demo/SKILL.md").write_text("# Demo\n\nStep one, team wording.\n")
        code, report, _ = self.tool("status")
        self.assertEqual((code, self.actions(report)["SKILL.md"]), (0, "keep"))
        code, result, _ = self.tool("pull", "demo")
        self.assertEqual((code, result["kept"]), (0, ["SKILL.md"]))
        self.assertEqual(self.pack_file("SKILL.md"), "# Demo\n\nStep one, team wording.\n")

    def test_both_changed_conflict_is_left_untouched_until_resolved(self):
        (self.root / PACK / "skills/demo/SKILL.md").write_text("# Demo\n\nTeam wording.\n")
        old_base = self.base("SKILL.md")
        self.advance({"Skills/demo/SKILL.md": "# Demo\n\nUpstream wording.\n"})
        code, report, _ = self.tool("status")
        self.assertEqual((code, self.actions(report)["SKILL.md"]), (1, "conflict"))
        code, result, _ = self.tool("pull", "demo")
        self.assertEqual(code, 1)
        self.assertEqual(result["conflicts"], [{"file": "SKILL.md", "state": "differs", "change": "both"}])
        self.assertEqual(self.pack_file("SKILL.md"), "# Demo\n\nTeam wording.\n")
        self.assertEqual(self.base("SKILL.md"), old_base)
        code, diff, _ = self.tool("diff", "demo")
        self.assertEqual(code, 1)
        self.assertIn("-Upstream wording.", diff["files"][0]["diff"])
        self.assertIn("+Team wording.", diff["files"][0]["diff"])
        code, resolved, _ = self.tool("resolve", "demo")  # the merged pack copy is final
        self.assertEqual((code, resolved["resolved"]), (0, ["SKILL.md"]))
        code, report, _ = self.tool("status")
        self.assertEqual((code, self.actions(report)["SKILL.md"]), (0, "keep"))

    def test_privacy_guard_refuses_and_leaves_the_pack_file(self):
        self.advance({"Skills/demo/SKILL.md": f"# Demo\n\nSee {PRIVATE_PATH}.\n"})
        old_base = self.base("SKILL.md")
        code, result, _ = self.tool("pull", "demo")
        self.assertEqual(code, 1)
        self.assertEqual(result["pulled"], [])
        self.assertEqual(result["refused"][0]["file"], "SKILL.md")
        self.assertIn("home path", result["refused"][0]["findings"][0])
        self.assertNotIn(PRIVATE_PATH, json.dumps(result))  # findings are redacted
        self.assertIn("Neutralize", result["next"])
        self.assertEqual(self.pack_file("SKILL.md"), "# Demo\n\nStep one.\n")
        self.assertEqual(self.base("SKILL.md"), old_base)
        # A neutralized pack copy can then be recorded as the merge of that upstream change.
        (self.root / PACK / "skills/demo/SKILL.md").write_text("# Demo\n\nSee <notes>.\n")
        self.assertEqual(self.tool("resolve", "demo", "--files", "SKILL.md")[0], 0)
        self.assertEqual(self.tool("status")[0], 0)

    # --- in-process helpers for failure injection -------------------------------------------

    def in_process(self):
        module = load_module()
        pack = module.Pack(self.root, self.config)
        upstream = module.Upstream(self.up, "origin/main")
        pack.forbid(upstream.real)
        return module, pack, upstream

    def failing_guard(self, module, suffix, call):
        """Real guard, except the CALL-th check of a path ending in SUFFIX reports a finding."""
        real, calls = module.guard_issues, {}

        def fake(published, data, root=None):
            calls[published] = calls.get(published, 0) + 1
            if published.endswith(suffix) and calls[published] == call:
                return ["privacy: forced finding"]
            return real(published, data, root)
        return fake

    def tree(self):
        """Every byte, mode and the state file of the package, for all-or-nothing assertions."""
        return {p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mode)
                for p in sorted(self.root.rglob("*")) if p.is_file() or p.is_symlink()}

    def two_file_change(self):
        self.advance({"Skills/demo/SKILL.md": "# Demo v2\n", "Skills/demo/references/notes.md": "Notes v2.\n"})
        return self.tree()

    def test_guard_failure_after_write_restores_every_file_and_the_state(self):
        before = self.two_file_change()
        module, pack, upstream = self.in_process()
        with mock.patch.object(module, "guard_issues", self.failing_guard(module, "references/notes.md", 2)):
            result = module.pull(pack, upstream, "demo", None)
        self.assertEqual(result["refused"], [{"file": "references/notes.md", "findings": ["privacy: forced finding"],
                                              "reverted": True}])
        self.assertEqual(result["pulled"], [])
        self.assertEqual(self.tree(), before)

    def test_write_error_on_a_later_file_restores_the_earlier_ones(self):
        before = self.two_file_change()
        module, pack, upstream = self.in_process()
        real, calls = module.atomic_write, []

        def flaky(target, *args):
            calls.append(target.name)
            if len(calls) == 2:
                raise OSError(28, "No space left on device")
            return real(target, *args)
        with mock.patch.object(module, "atomic_write", flaky):
            with self.assertRaisesRegex(module.PackSyncError, "all changes were restored"):
                module.pull(pack, upstream, "demo", None)
        self.assertEqual(self.tree(), before)

    def test_state_save_failure_restores_the_files(self):
        before = self.two_file_change()
        module, pack, upstream = self.in_process()
        real = module.atomic_write

        def no_state(target, data, *args):
            if target.name == "pack-sync.json":
                raise OSError(13, "Permission denied")
            return real(target, data, *args)
        with mock.patch.object(module, "atomic_write", no_state):
            with self.assertRaises(module.PackSyncError):
                module.pull(pack, upstream, "demo", None)
        self.assertEqual(self.tree(), before)
        # A finding in the written state file restores everything as well.
        module, pack, upstream = self.in_process()
        with mock.patch.object(module, "guard_issues", self.failing_guard(module, "pack-sync.json", 2)):
            result = module.pull(pack, upstream, "demo", None)
        self.assertTrue(result["refused"][0]["reverted"])
        self.assertEqual(self.tree(), before)

    def test_state_file_is_guarded_before_writing(self):
        config = json.loads(self.config.read_text())
        config["known_candidates"]["other"] = f"see {PRIVATE_PATH}"
        self.config.write_text(json.dumps(config, indent=2))
        before = self.two_file_change()
        code, result, _ = self.tool("pull", "demo")
        self.assertEqual(code, 1)
        self.assertEqual(result["refused"][0]["file"], PACK + "/pack-sync.json")
        self.assertEqual(self.tree(), before)

    def test_one_conflict_in_the_selection_writes_nothing(self):
        (self.root / PACK / "skills/demo/references/notes.md").write_text("Team notes.\n")
        before = self.two_file_change()
        code, result, _ = self.tool("pull", "demo")
        self.assertEqual(code, 1)
        self.assertEqual([c["file"] for c in result["conflicts"]], ["references/notes.md"])
        self.assertEqual(result["blocked"], ["SKILL.md"])
        self.assertEqual(self.tree(), before)
        code, result, _ = self.tool("pull", "demo", "--files", "SKILL.md")  # the clean file alone
        self.assertEqual((code, self.pack_file("SKILL.md")), (0, "# Demo v2\n"))

    def test_adopt_rechecks_written_files_and_restores(self):
        self.advance({"Skills/fresh/SKILL.md": "# Fresh\n", "Skills/fresh/b.md": "B\n"})
        before = self.tree()
        module, pack, upstream = self.in_process()
        with mock.patch.object(module, "guard_issues", self.failing_guard(module, "fresh/b.md", 2)):
            result = module.adopt(pack, upstream, "fresh", None, False)
        self.assertFalse(result["adopted"])
        self.assertTrue(result["refused"][0]["reverted"])
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.root / PACK / "skills/fresh").exists())

    # --- destinations ------------------------------------------------------------------------

    def test_adopt_rejects_escaping_and_odd_names(self):
        self.advance({"Skills/fresh/SKILL.md": "# Fresh\n"})
        before = self.tree()
        for name in ("../../../../escaped", "/tmp/escaped", "a/b", "..", ".", "", " x", "x\nfoo"):
            code, _, err = self.tool("adopt", "fresh", "--as", name)
            self.assertEqual(code, 2, name)
            self.assertIn("invalid", err)
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.root.parent / "escaped").exists())

    def test_config_under_a_symlinked_package_parent_is_normalized(self):
        alias = self.root.parent / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        module = load_module()
        pack = module.Pack(alias, alias / PACK / "pack-sync.json")
        self.assertEqual(pack.root, self.root.resolve())
        self.assertEqual(pack.config_name, PACK + "/pack-sync.json")

    def test_config_paths_are_validated(self):
        for change in ({"pack_root": "/tmp/somewhere"}, {"pack_root": PACK + "/../../.."},
                       {"skills": {"../demo": {"upstream": "demo"}}},
                       {"skills": {"demo": {"upstream": "demo", "files": {"../../x": {}}}}}):
            config = json.loads(self.config.read_text())
            saved = self.config.read_text()
            config.update(change)
            self.config.write_text(json.dumps(config))
            code, _, err = self.tool("status")
            self.assertEqual(code, 2, change)
            self.assertIn("invalid", err)
            self.config.write_text(saved)

    def test_refuses_destinations_inside_the_upstream_checkout(self):
        other = self.root.parent / "other-upstream"
        subprocess.run(["git", "clone", "-q", str(self.source), str(other)], check=True, env=GIT_ENV)
        package = other / "package"
        (package / PACK / "skills/demo").mkdir(parents=True)
        (package / PACK / "pack-sync.json").write_text(self.config.read_text())
        out = subprocess.run([sys.executable, str(SCRIPT), "--root", str(package), "--upstream", str(other),
                              "status"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("inside the upstream checkout", out.stderr)

    def test_symlinked_skill_folder_is_refused(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "SKILL.md").write_text("# Demo\n\nStep one.\n")
        skill = self.root / PACK / "skills/demo"
        for path in sorted(skill.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        skill.rmdir()
        skill.symlink_to(outside, target_is_directory=True)
        self.advance({"Skills/demo/SKILL.md": "# Demo v2\n"})
        code, _, err = self.tool("pull", "demo")
        self.assertEqual(code, 2)
        self.assertIn("symlink", err)
        self.assertEqual((outside / "SKILL.md").read_text(), "# Demo\n\nStep one.\n")

    def test_symlinked_ancestor_folder_is_refused(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (self.root / PACK / "skills/demo/extra").symlink_to(outside, target_is_directory=True)
        self.advance({"Skills/demo/extra/new.md": "New.\n"})
        code, result, _ = self.tool("pull", "demo")  # the linked folder is unsupported: a conflict
        self.assertEqual((code, result["conflicts"][0]["file"]), (1, "extra"))
        code, _, err = self.tool("pull", "demo", "--files", "extra/new.md")
        self.assertEqual(code, 2)
        self.assertIn("symlink in the destination path", err)
        self.assertEqual(list(outside.iterdir()), [])

    def test_temporary_file_never_follows_a_planted_symlink(self):
        victim = self.root.parent / "victim.txt"
        victim.write_text("untouched\n")
        (self.root / PACK / "skills/demo/SKILL.md.pack-sync-tmp").symlink_to(victim)
        self.advance({"Skills/demo/SKILL.md": "# Demo v2\n"})
        code, _, _ = self.tool("pull", "demo", "--files", "SKILL.md")
        self.assertEqual((code, self.pack_file("SKILL.md")), (0, "# Demo v2\n"))
        self.assertEqual(victim.read_text(), "untouched\n")
        self.assertFalse((self.root / PACK / "skills/demo/SKILL.md").is_symlink())
        leftovers = [p.name for p in (self.root / PACK / "skills/demo").iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    # --- modes and deletions -----------------------------------------------------------------

    def test_mode_change_is_tracked_and_applied(self):
        script = self.source / "Skills/demo/run.sh"
        script.write_text("echo ok\n")
        self.advance({})
        self.assertEqual(self.tool("pull", "demo")[0], 0)
        target = self.root / PACK / "skills/demo/run.sh"
        self.assertFalse(target.stat().st_mode & 0o111)
        os.chmod(script, 0o755)
        git(self.source, "update-index", "--chmod=+x", "Skills/demo/run.sh")
        self.advance({})
        code, report, _ = self.tool("status")
        self.assertEqual((code, self.actions(report)["run.sh"]), (1, "pull"))
        self.assertEqual(self.tool("pull", "demo")[0], 0)
        self.assertTrue(target.stat().st_mode & 0o100)
        self.assertEqual(target.stat().st_mode & 0o077 & ~0o055, 0)  # temp-file 0600 never leaks, nothing extra
        self.assertEqual(self.base("run.sh")["base_mode"], "100755")
        self.assertEqual(self.tool("status")[0], 0)
        os.chmod(target, 0o644)  # a pack-only mode change is a local change
        self.assertEqual(self.actions(self.tool("status")[1])["run.sh"], "keep")

    def test_mutual_deletion_advances_the_base(self):
        (self.root / PACK / "skills/demo/references/notes.md").unlink()
        self.advance({}, delete=["Skills/demo/references/notes.md"])
        code, report, _ = self.tool("status")
        self.assertEqual((code, self.actions(report)["references/notes.md"]), (1, "record"))
        code, result, _ = self.tool("pull", "demo")
        self.assertEqual((code, result["recorded"]), (0, ["references/notes.md"]))
        self.assertIsNone(self.base("references/notes.md")["base_sha256"])
        self.assertEqual(self.tool("status")[0], 0)
        self.advance({"Skills/demo/references/notes.md": "Notes.\n"})  # upstream restores the same bytes
        code, report, _ = self.tool("status")
        self.assertEqual((code, self.actions(report)["references/notes.md"]), (1, "pull"))

    def test_failed_empty_folder_cleanup_after_commit_is_a_warning(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root ignores folder permissions")
        self.advance({}, delete=["Skills/demo/references/notes.md"])
        skill = self.root / PACK / "skills/demo"
        os.chmod(skill, 0o555)  # references/ empties but cannot be removed from its parent
        self.addCleanup(os.chmod, skill, 0o755)
        code, result, err = self.tool("pull", "demo")
        self.assertEqual(code, 0, err)
        self.assertEqual(result["pulled"], [{"file": "references/notes.md", "operation": "deleted"}])
        self.assertEqual(result["warnings"], [f"committed; empty folder not removed: {PACK}/skills/demo/references"])
        self.assertIsNone(self.base("references/notes.md")["base_sha256"])
        os.chmod(skill, 0o755)
        self.assertEqual(self.tool("status")[0], 0)

    def assert_restructure_refused(self, files):
        before = self.tree()
        code, report, _ = self.tool("status")
        self.assertEqual(code, 1)
        self.assertEqual({f: self.actions(report)[f] for f in files}, {f: "restructure" for f in files})
        code, result, err = self.tool("pull", "demo")
        self.assertEqual(code, 1, err)
        self.assertEqual(sorted(c["file"] for c in result["conflicts"]), sorted(files))
        self.assertIn("restructure", result["next"])
        self.assertEqual(self.tree(), before)

    def test_file_replaced_by_folder_is_a_restructure(self):
        self.advance({"Skills/demo/references/notes.md/detail.md": "Detail.\n"},
                     delete=["Skills/demo/references/notes.md"])
        self.assert_restructure_refused(["references/notes.md", "references/notes.md/detail.md"])
        # Manual recovery: remove the old pack file, then pull.
        (self.root / PACK / "skills/demo/references/notes.md").unlink()
        self.assertEqual(self.tool("pull", "demo")[0], 0)
        self.assertEqual(self.pack_file("references/notes.md/detail.md"), "Detail.\n")
        self.assertEqual(self.tool("status")[0], 0)

    def test_folder_replaced_by_file_is_a_restructure(self):
        self.advance({"Skills/demo/references/notes.md/detail.md": "Detail.\n"},
                     delete=["Skills/demo/references/notes.md"])
        (self.root / PACK / "skills/demo/references/notes.md").unlink()
        self.assertEqual(self.tool("pull", "demo")[0], 0)
        self.advance({"Skills/demo/references/notes.md": "Notes again.\n"},
                     delete=["Skills/demo/references/notes.md/detail.md"])
        self.assert_restructure_refused(["references/notes.md", "references/notes.md/detail.md"])
        detail = self.root / PACK / "skills/demo/references/notes.md/detail.md"
        detail.unlink()
        detail.parent.rmdir()
        self.assertEqual(self.tool("pull", "demo")[0], 0)
        self.assertEqual(self.pack_file("references/notes.md"), "Notes again.\n")
        self.assertEqual(self.tool("status")[0], 0)

    def test_missing_upstream_names_the_lookup_without_the_path(self):
        config = json.loads(self.config.read_text())
        config["upstream"]["checkout_hint"] = str(self.root.parent / "private-marker-checkout")
        self.config.write_text(json.dumps(config))
        env = {k: v for k, v in os.environ.items() if k != "PACK_SYNC_UPSTREAM"}
        out = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "status"],
                             capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 2)
        for name in ("checkout_hint", "--upstream", "$PACK_SYNC_UPSTREAM"):
            self.assertIn(name, out.stderr)
        self.assertNotIn("private-marker", out.stderr)
        env["PACK_SYNC_UPSTREAM"] = str(self.up)
        out = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "status"],
                             capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_global_options_after_the_command(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "status", "--json", "--root", str(self.root),
                              "--upstream", str(self.up)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(json.loads(out.stdout)["in_sync"])
        out = subprocess.run([sys.executable, str(SCRIPT), "--json", "diff", "demo", "--root", str(self.root),
                              "--upstream", str(self.up)], capture_output=True, text=True)
        self.assertEqual((out.returncode, json.loads(out.stdout)["files"]), (0, []))

    def test_adopt_new_skill_and_refuse_private_one(self):
        self.advance({"Skills/fresh/SKILL.md": "# Fresh\n", "Skills/fresh/scripts/run.sh": "echo ok\n",
                      "Skills/leaky/SKILL.md": f"# Leaky\n{PRIVATE_PATH}\n"})
        code, report, _ = self.tool("status")
        self.assertEqual(code, 1)
        self.assertEqual({c["name"]: c["known"] for c in report["candidates"]},
                         {"other": True, "fresh": False, "leaky": False})
        code, result, _ = self.tool("adopt", "fresh")
        self.assertEqual((code, result["adopted"], result["copied"]), (0, True, ["SKILL.md", "scripts/run.sh"]))
        self.assertEqual((self.root / PACK / "skills/fresh/scripts/run.sh").read_text(), "echo ok\n")
        code, result, _ = self.tool("adopt", "leaky")
        self.assertEqual((code, result["adopted"]), (1, False))
        self.assertFalse((self.root / PACK / "skills/leaky").exists())
        self.assertNotIn("leaky", json.loads(self.config.read_text())["skills"])
        leaky = self.root / PACK / "skills/leaky"
        leaky.mkdir()
        (leaky / "SKILL.md").write_text("# Leaky\n<notes>\n")
        code, result, _ = self.tool("adopt", "leaky", "--keep-pack")
        self.assertEqual((code, result["adopted"], result["copied"]), (0, True, []))
        code, report, _ = self.tool("status")
        self.assertEqual(code, 0)
        self.assertEqual(self.actions(report, "fresh"), {"SKILL.md": "in-sync", "scripts/run.sh": "in-sync"})
        self.assertEqual(self.actions(report, "leaky"), {"SKILL.md": "keep"})
        self.assertEqual(self.tool("adopt", "fresh")[0], 2)  # already tracked

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.tool("pull", "missing")[0], 2)
        self.assertEqual(self.tool("pull", "demo", "--files", "nope.md")[0], 2)
        out = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--upstream",
                              str(self.root / "absent"), "status"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("upstream checkout from --upstream not found", out.stderr)
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT)], capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
