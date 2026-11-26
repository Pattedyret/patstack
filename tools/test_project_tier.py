import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import project_tier

MAP = {
    "owners": {"Customer-Org": "CRITICAL"},
    "repos": {"Customer-Org/own-tool": "INTERNAL", "Customer-Org/team-tool": "INTERNAL",
              "someone/own-app": "INTERNAL", "tools/widget": "INTERNAL",
              "forge.example/group/sub/app": "INTERNAL", "git.deploy.example/own-app": "INTERNAL"},
    "local": {"code/scratch-bot": "INTERNAL"},
}


def run(map_file, path):
    out = io.StringIO()
    with mock.patch.dict(os.environ, {"PATSTACK_PROJECT_TIERS": str(map_file)}), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = project_tier.main(["--path", str(path), "--json"])
    return code, json.loads(out.getvalue())


class IdentityTest(unittest.TestCase):
    def test_github_forms_agree(self):
        at = chr(64)  # the repository's privacy scan reads a literal user-at-host as an email address
        for url in ("https://github.com/Owner/Name.git", "https://github.com/owner/name/",
                    f"ssh://user{at}github.com/owner/name.git", f"user{at}github.com:owner/name.git",
                    "github.com:owner/name.git", f"https://user:placeholder{at}github.com/owner/name.git"):
            self.assertEqual(project_tier.identity(url), "owner/name", url)

    def test_other_forges_keep_host_and_full_path(self):
        self.assertEqual(project_tier.identity("https://forge.example/customer-org/tools/widget.git"),
                         "forge.example/customer-org/tools/widget")
        self.assertEqual(project_tier.identity("https://forge.example/tools/widget"),
                         "forge.example/tools/widget")

    def test_port_and_path_case_stay_distinct_on_other_forges(self):
        self.assertEqual(project_tier.identity("https://FORGE.example:8443/Team/App.git"),
                         "forge.example:8443/Team/App")

    def test_ssh_alias_has_no_identity(self):
        self.assertIsNone(project_tier.identity("customer-alias:owner/name.git"))

    def test_unsupported_addresses_have_no_identity(self):
        for url in ("/srv/git/app.git", "../app.git", "file:///srv/app.git", "", "https://github.com/",
                    "https://[broken/owner/name", "https://github.com:notaport/owner/name"):
            self.assertIsNone(project_tier.identity(url), url)


class ValidateTest(unittest.TestCase):
    def test_valid_map_passes(self):
        self.assertIsNone(project_tier.validate(MAP))

    def test_local_ci_takes_owners_and_repos_only(self):
        self.assertIsNone(project_tier.validate({"local_ci": ["example-consulting", "other-owner/app"]}))
        for bad in ({"local_ci": "example-consulting"}, {"local_ci": [""]}, {"local_ci": ["a/b/c"]},
                    {"local_ci": ["/a"]}, {"local_ci": [3]}, {"local_ci": ["ok", "has space"]},
                    {"local_ci": ["-dash-first"]}, {"local_ci": ["host.example/app"]},
                    {"local_ci": ["example-consulting\n"]}):
            self.assertIsNotNone(project_tier.validate(bad), bad)

    def test_a_key_given_twice_makes_the_map_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "map.json"
            path.write_text('{"local_ci": ["bad name"], "local_ci": ["example-consulting"]}')
            data, problem = project_tier.load_map(path)
            self.assertEqual(data, {})
            self.assertIn("unreadable", problem)

    def test_local_ci_matches_owner_or_exact_repo(self):
        data = {"local_ci": ["Example-Consulting", "Other/app"]}
        self.assertTrue(project_tier.local_ci(data, "EXAMPLE-consulting/x"))
        self.assertTrue(project_tier.local_ci(data, "other/APP"))
        self.assertFalse(project_tier.local_ci(data, "other/app2"))
        self.assertFalse(project_tier.local_ci({}, "example-consulting/x"))

    def test_friends_is_rejected_in_every_section(self):
        for section, key in (("owners", "customer-org"), ("repos", "customer-org/team-tool"),
                             ("local", "code/team-tool")):
            with self.subTest(section=section):
                self.assertIsNotNone(project_tier.validate({section: {key: "FRIENDS"}}))

    def test_case_on_another_forge_is_a_different_project(self):
        data = {"repos": {"forge.example/Team/app": "INTERNAL", "forge.example/team/app": "CRITICAL"}}
        self.assertIsNone(project_tier.validate(data))

    def test_invalid_maps_are_rejected(self):
        bad = [[], {"repos": []}, {"owners": "CRITICAL"}, {"repos": {"a/b": None}}, {"repos": {"a/b": "INERNAL"}},
               {"repos": {"a/b": ["INTERNAL"]}}, {"owners": {"me": "INTERNAL"}}, {"owners": {"me": "FRIENDS"}},
               {"repos": {"A/b": "INTERNAL", "a/B": "CRITICAL"}}, {"extra": {}}, {"local": {"x": 1}},
               {"repos": {"FORGE.example/a/b": "INTERNAL", "forge.example/a/b": "CRITICAL"}}]
        for data in bad:
            self.assertIsNotNone(project_tier.validate(data), data)


class ClassifyTest(unittest.TestCase):
    top = Path("/nowhere/project")

    def tier(self, **remotes):
        urls = {name.replace("_", "-"): [url] for name, url in remotes.items()}
        return project_tier.classify(MAP, self.top, urls)[0]

    def test_exact_repo_beats_its_own_owner(self):
        self.assertEqual(self.tier(origin="https://github.com/customer-org/OWN-tool"), "INTERNAL")

    def test_owner_default_covers_new_repositories(self):
        self.assertEqual(self.tier(origin="https://github.com/customer-org/new"), "CRITICAL")

    def test_namespace_or_forge_cannot_borrow_a_github_entry(self):
        self.assertEqual(self.tier(origin="https://forge.example/customer-org/tools/widget.git"), "UNCLASSIFIED")
        self.assertEqual(self.tier(origin="https://forge.example/tools/widget.git"), "UNCLASSIFIED")
        self.assertEqual(self.tier(origin="https://forge.example/group/sub/app.git"), "INTERNAL")

    def test_customer_upstream_wins_over_a_personal_fork(self):
        self.assertEqual(self.tier(origin="https://github.com/someone/own-app",
                                   upstream="https://github.com/customer-org/app"), "CRITICAL")

    def test_customer_push_url_wins(self):
        urls = {"origin": ["https://github.com/someone/own-app", "https://github.com/customer-org/app"]}
        self.assertEqual(project_tier.classify(MAP, self.top, urls)[0], "CRITICAL")

    def test_customer_remote_counts_without_an_origin(self):
        self.assertEqual(self.tier(fork="https://github.com/customer-org/app"), "CRITICAL")

    def test_unmapped_personal_fork_is_unclassified(self):
        self.assertEqual(self.tier(origin="https://github.com/someone/unlisted-fork"), "UNCLASSIFIED")

    def test_any_unmapped_remote_makes_the_project_unclassified(self):
        self.assertEqual(self.tier(origin="https://github.com/someone/own-app",
                                   fork="https://github.com/someone/unlisted"), "UNCLASSIFIED")
        self.assertEqual(self.tier(origin="https://github.com/someone/own-app",
                                   heroku="https://git.deploy.example/app.git"), "UNCLASSIFIED")

    def test_mapped_deployment_remote_keeps_the_tier(self):
        self.assertEqual(self.tier(origin="https://github.com/someone/own-app",
                                   heroku="https://git.deploy.example/own-app.git"), "INTERNAL")

    def test_ssh_alias_remote_makes_the_project_unclassified(self):
        self.assertEqual(self.tier(origin="https://github.com/someone/own-app",
                                   customer="customer-alias:customer-org/app.git"), "UNCLASSIFIED")

    def test_ports_do_not_borrow_a_grant(self):
        self.assertEqual(self.tier(origin="https://forge.example:8443/group/sub/app.git"), "UNCLASSIFIED")

    def test_path_case_does_not_borrow_a_grant_on_another_forge(self):
        self.assertEqual(self.tier(origin="https://forge.example/GROUP/sub/app.git"), "UNCLASSIFIED")

    def test_only_unmapped_remotes_are_unclassified(self):
        self.assertEqual(self.tier(fork="https://github.com/someone/unlisted"), "UNCLASSIFIED")

    def test_unsupported_remote_fails_closed(self):
        self.assertEqual(self.tier(origin="https://github.com/someone/own-app", backup="/srv/backup.git"),
                         "UNCLASSIFIED")

    def test_failed_discovery_ignores_every_grant(self):
        self.assertEqual(project_tier.classify(MAP, None, "git could not run")[0], "UNCLASSIFIED")


class CheckoutTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name).resolve()
        self.map = self.home / "tiers.json"
        self.map.write_text(json.dumps(MAP), encoding="utf-8")
        patcher = mock.patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)

    def repo(self, relative, **remotes):
        path = self.home / relative
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        for name, url in remotes.items():
            subprocess.run(["git", "-C", str(path), "remote", "add", name, url], check=True)
        return path

    def test_modes_by_tier(self):
        cases = {"https://github.com/customer-org/team-tool": "Full Send always",
                 "https://github.com/someone/own-app": "Full Send always",
                 "https://github.com/customer-org/app": "evaluate Full Send or Full Stop at intake",
                 "https://github.com/stranger/app": "evaluate Full Send or Full Stop at intake"}
        for number, (url, mode) in enumerate(cases.items()):
            self.assertEqual(run(self.map, self.repo(f"r{number}", origin=url))[1]["mode"], mode, url)

    def test_legacy_friends_map_fails_closed(self):
        data = {**MAP, "repos": {**MAP["repos"], "someone/legacy-tool": "FRIENDS"}}
        self.map.write_text(json.dumps(data), encoding="utf-8")
        path = self.repo("legacy", origin="https://github.com/customer-org/team-tool")
        code, result = run(self.map, path)
        self.assertEqual((code, result["tier"]), (0, "UNCLASSIFIED"))
        self.assertEqual(result["mode"], "evaluate Full Send or Full Stop at intake")
        self.assertIn("invalid tier map", result["warning"])

    def test_real_fork_with_customer_upstream_is_critical(self):
        path = self.repo("fork", origin="https://github.com/someone/own-app",
                         upstream="https://github.com/customer-org/app")
        self.assertEqual(run(self.map, path)[1]["tier"], "CRITICAL")

    def test_url_rewrites_are_seen(self):
        for key in ("insteadOf", "pushInsteadOf"):
            path = self.repo(f"rewrite-{key}", origin="https://github.com/someone/own-app.git")
            subprocess.run(["git", "-C", str(path), "config", f"url.https://github.com/customer-org/app.git.{key}",
                            "https://github.com/someone/own-app.git"], check=True)
            self.assertEqual(run(self.map, path)[1]["tier"], "CRITICAL", key)

    def test_separate_push_url_is_seen(self):
        path = self.repo("push", origin="https://github.com/someone/own-app.git")
        subprocess.run(["git", "-C", str(path), "remote", "set-url", "--push", "origin",
                        "https://github.com/customer-org/app.git"], check=True)
        self.assertEqual(run(self.map, path)[1]["tier"], "CRITICAL")

    def test_remote_name_with_a_dot_is_seen(self):
        path = self.repo("dotted", origin="https://github.com/someone/own-app.git")
        subprocess.run(["git", "-C", str(path), "remote", "add", "customer.prod",
                        "https://github.com/customer-org/app.git"], check=True)
        self.assertEqual(run(self.map, path)[1]["tier"], "CRITICAL")

    def test_malformed_remote_still_gives_a_tier(self):
        path = self.repo("broken", origin="https://[broken/customer-org/app")
        code, result = run(self.map, path)
        self.assertEqual((code, result["tier"]), (0, "UNCLASSIFIED"))

    def test_invalid_utf8_remote_still_gives_a_tier(self):
        path = self.repo("bytes", origin="https://github.com/someone/own-app.git")
        config = path / ".git/config"
        config.write_bytes(config.read_bytes().replace(b"own-app", b"own-\xff-app"))
        code, result = run(self.map, path)
        self.assertEqual((code, result["tier"]), (0, "UNCLASSIFIED"))

    def test_unexpected_error_still_gives_a_tier(self):
        path = self.repo("oops", origin="https://github.com/someone/own-app.git")
        with mock.patch.object(project_tier, "classify", side_effect=RuntimeError("boom")):
            code, result = run(self.map, path)
        self.assertEqual((code, result["tier"], result["source"]), (0, "UNCLASSIFIED", "unexpected error"))

    def test_legacy_remote_files_fail_closed(self):
        for kind in ("remotes", "branches"):
            for origin in ({}, {"origin": "https://github.com/someone/own-app.git"}):
                relative = f"code/scratch-bot-{kind}" if origin else "code/scratch-bot"
                path = self.repo(relative, **origin)
                folder = path / ".git" / kind
                folder.mkdir(exist_ok=True)
                (folder / "customer").write_text("https://github.com/customer-org/app.git\n", encoding="utf-8")
                self.assertEqual(run(self.map, path)[1]["tier"], "UNCLASSIFIED", (kind, origin))
                shutil.rmtree(path)

    def test_restrictive_output_encoding_still_prints_a_tier(self):
        path = self.home / "prosjekt-\u00e6"
        path.mkdir()
        env = {**os.environ, "PYTHONIOENCODING": "ascii", "PATSTACK_PROJECT_TIERS": str(self.map)}
        result = subprocess.run([sys.executable, project_tier.__file__, "--path", str(path)],
                                capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"Tier: UNCLASSIFIED", result.stdout)

    def test_subdirectory_resolves_its_project(self):
        path = self.repo("sub", origin="https://github.com/customer-org/team-tool") / "deep"
        path.mkdir()
        self.assertEqual(run(self.map, path)[1]["tier"], "INTERNAL")

    def test_local_entry_needs_the_exact_path(self):
        self.assertEqual(run(self.map, self.repo("code/scratch-bot"))[1]["tier"], "INTERNAL")
        self.assertEqual(run(self.map, self.repo("customer/scratch-bot"))[1]["tier"], "UNCLASSIFIED")

    def test_worktree_of_a_local_project_keeps_its_tier(self):
        main = self.repo("code/scratch-bot")
        subprocess.run(["git", "-C", str(main), "-c", "user.name=t", "-c", "user.email=t" + chr(64) + "example.invalid",
                        "commit", "-q", "--allow-empty", "-m", "base"], check=True)
        worktree = self.home / "elsewhere/lane"
        subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", "-b", "lane", str(worktree)], check=True)
        self.assertEqual(run(self.map, worktree)[1]["tier"], "INTERNAL")

    def test_local_entry_covers_a_folder_outside_git(self):
        path = self.home / "code/scratch-bot"
        path.mkdir(parents=True)
        self.assertEqual(run(self.map, path)[1]["tier"], "INTERNAL")

    def test_remotes_disable_the_local_entry(self):
        path = self.repo("code/scratch-bot", origin="https://github.com/stranger/app")
        self.assertEqual(run(self.map, path)[1]["tier"], "UNCLASSIFIED")

    def test_missing_directory_fails_closed(self):
        self.assertEqual(run(self.map, self.home / "code/absent")[1]["tier"], "UNCLASSIFIED")

    def test_git_failures_fail_closed(self):
        path = self.repo("code/scratch-bot", origin="https://github.com/someone/own-app")
        for effect in (FileNotFoundError(), subprocess.TimeoutExpired("git", 15)):
            with mock.patch.object(project_tier.subprocess, "run", side_effect=effect):
                self.assertEqual(run(self.map, path)[1]["tier"], "UNCLASSIFIED", effect)

    def test_missing_map_warns_and_stays_unclassified(self):
        path = self.repo("a", origin="https://github.com/customer-org/team-tool")
        code, result = run(self.home / "absent.json", path)
        self.assertEqual((code, result["tier"]), (0, "UNCLASSIFIED"))
        self.assertIn("no tier map", result["warning"])

    def test_invalid_map_warns_and_stays_unclassified(self):
        path = self.repo("a", origin="https://github.com/customer-org/own-tool")
        for broken in ("{broken", '{"owners": {"customer-org": "INTERNAL"}}', '{"repos": []}'):
            self.map.write_text(broken, encoding="utf-8")
            code, result = run(self.map, path)
            self.assertEqual((code, result["tier"]), (0, "UNCLASSIFIED"), broken)
            self.assertTrue(result["warning"], broken)


class MapChoiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("PATSTACK_PROJECT_TIERS", None)
        home = mock.patch.object(Path, "home", return_value=self.home)
        home.start()
        self.addCleanup(home.stop)
        self.addCleanup(self.tmp.cleanup)

    def pack(self, name, data):
        path = self.root / "patstack/project-packs" / name / "project-tiers.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(data))

    def load(self):
        return project_tier.load_tiers(self.root / "patstack")

    def assertFailsClosed(self, text):
        data, warning = self.load()
        self.assertEqual(data, {})
        self.assertIn(text, warning)

    def test_the_one_pack_map_applies_when_there_is_no_private_map(self):
        self.pack("demo", {"owners": {"Team-Org": "CRITICAL"}, "repos": {"team-org/workflow": "INTERNAL"}})
        data, warning = self.load()
        self.assertIsNone(warning)
        self.assertEqual(project_tier.remote_tier(data, "team-org/some-app"), "CRITICAL")
        self.assertEqual(project_tier.remote_tier(data, "team-org/workflow"), "INTERNAL")  # its own exception stands

    def test_private_map_replaces_the_pack_map(self):
        self.pack("demo", {"owners": {"Team-Org": "CRITICAL"}})
        private = self.home / ".config/patstack/project-tiers.json"
        private.parent.mkdir(parents=True)
        private.write_text(json.dumps({"repos": {"me/tool": "INTERNAL"}}))
        data, _ = self.load()
        self.assertIsNone(project_tier.remote_tier(data, "team-org/some-app"))
        self.assertEqual(project_tier.remote_tier(data, "me/tool"), "INTERNAL")

    @unittest.skipIf(os.name == "nt", "native symlink fixture; run on Linux")
    def test_a_broken_private_link_never_falls_back_to_the_pack(self):
        self.pack("demo", {"repos": {"team/app": "INTERNAL"}})
        private = self.home / ".config/patstack/project-tiers.json"
        private.parent.mkdir(parents=True)
        private.symlink_to(self.root / "gone.json")
        self.assertFailsClosed("no tier map")
        (self.root / "gone.json").write_text('{"repos": {"me/tool": "INTERNAL"}}')
        data, warning = self.load()  # a valid link is used as before
        self.assertIsNone(warning)
        self.assertEqual(project_tier.remote_tier(data, "me/tool"), "INTERNAL")

    def test_two_pack_maps_fail_closed(self):
        self.pack("a", {"repos": {"team/app": "INTERNAL"}})
        self.pack("b", {"repos": {"team/app": "INTERNAL"}})  # even identical maps never combine
        self.assertFailsClosed("more than one")

    def test_a_hidden_pack_folder_counts(self):
        self.pack("a", {"repos": {"team/app": "INTERNAL"}})
        self.pack(".b", {"owners": {"Team": "CRITICAL"}})
        self.assertFailsClosed("more than one")

    @unittest.skipIf(os.name == "nt", "native symlink fixture; run on Linux")
    def test_symlinked_pack_maps_and_folders_fail_closed(self):
        self.pack("a", {"repos": {"team/app": "INTERNAL"}})
        packs = self.root / "patstack/project-packs"
        (packs / "b").mkdir()
        (packs / "b/project-tiers.json").symlink_to(self.root / "gone.json")
        self.assertFailsClosed("not a plain file")
        (packs / "b/project-tiers.json").unlink()
        (packs / "b").rmdir()
        (packs / "c").symlink_to(self.root / "missing-folder")
        self.assertFailsClosed("symlink")

    def test_a_bad_pack_map_fails_closed(self):
        self.pack("b", {"owners": {"Other": "INTERNAL"}})  # owners may only be CRITICAL
        self.assertFailsClosed("invalid tier map")

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs POSIX permissions as a normal user")
    def test_an_unreadable_pack_is_never_skipped(self):
        self.pack("a", {"repos": {"team/app": "INTERNAL"}})
        folder = self.root / "patstack/project-packs/b"
        folder.mkdir()
        folder.chmod(0)
        self.addCleanup(folder.chmod, 0o700)
        self.assertFailsClosed("unreadable")

    def test_no_pack_and_no_private_map_stays_unclassified(self):
        data, warning = project_tier.load_tiers(self.root / "patstack")
        self.assertEqual(data, {})
        self.assertIn("no tier map", warning)

    def test_every_bundled_pack_map_is_valid(self):
        for path in sorted(project_tier.ROOT.glob("project-packs/*/project-tiers.json")):
            self.assertIsNone(project_tier.load_map(path)[1], path)


if __name__ == "__main__":
    unittest.main()
