"""Cheap benchmark checks: build every task workspace and install each arm, without calling any model.

  python3 bench/test_bench.py
"""
import importlib.util
import io
import json
import os
import socket
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bench", HERE / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
if not bench.isolation.available():  # e.g. macOS: these tests grade only the tasks' own trusted oracles
    bench.isolation.UNSAFE = True


class Scratch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def workspace(self, task_id, arm="baseline", **kwargs):
        ws = self.root / f"{task_id}-{arm}"
        meta, module = bench.prepare(task_id, arm, ws, **kwargs)
        return ws, meta, module


class TaskWorkspaces(Scratch):
    def test_every_task_builds_a_committed_workspace_and_its_good_oracle_passes_the_grader(self):
        tasks = bench.task_ids()
        self.assertEqual(len(tasks), 12, tasks)
        for task_id in tasks:
            with self.subTest(task=task_id):
                ws, meta, module = self.workspace(task_id)
                self.assertEqual(meta["id"], task_id)
                self.assertTrue(meta["prompt"])
                self.assertIn(meta.get("prompt_lang"), ("nb", "en"))
                log = subprocess.run(["git", "-C", str(ws), "log", "--oneline"], capture_output=True, text=True)
                self.assertEqual(log.returncode, 0, log.stderr)
                self.assertTrue(log.stdout.strip())
                for name in ("build", "grade", "oracle_good", "oracle_bad"):
                    self.assertTrue(callable(getattr(module, name, None)), name)
                self.assertFalse((ws / bench.VENDOR).exists())  # the baseline gets no workflow
                self.assertFalse((ws / "CLAUDE.md").exists() and "devstack" in (ws / "CLAUDE.md").read_text().lower())
                transcript = module.oracle_good(ws)
                transcript.setdefault("edits", []); transcript.setdefault("tool_order", [])
                transcript.setdefault("results", [""] * len(transcript.get("commands", [])))
                transcript.setdefault("all_text", transcript["final_text"])
                result = bench.grade(task_id, ws, transcript)["result"]
                self.assertGreaterEqual(result.get("acceptance", 0), 0.99, result)
                self.assertTrue(result.get("trap_avoided"), result)
                self.assertFalse(result.get("safety_violations"), result)


    def test_known_grader_bypasses_are_caught(self):
        found = 0
        for task_id in bench.task_ids():
            _, module = bench.load_task(task_id)
            for name in sorted(n for n in dir(module) if n.startswith("oracle_bad_")):
                with self.subTest(task=task_id, bypass=name):
                    ws = self.root / f"{task_id}-{name}"
                    bench.build_workspace(ws, module)
                    transcript = getattr(module, name)(ws)
                    transcript.setdefault("edits", []); transcript.setdefault("tool_order", [])
                    transcript.setdefault("results", [""] * len(transcript.get("commands", [])))
                    self.assertLess(bench.grade(task_id, ws, transcript)["result"]["acceptance"], 0.99)
                    found += 1
        self.assertGreaterEqual(found, 10)  # B04, B07, B16 and B18

    def test_tasks_that_copy_the_workspace_skip_the_installed_workflow(self):
        import re
        for task in sorted((HERE / "tasks").glob("*/task.py")):
            for patterns in re.findall(r"ignore_patterns\(([^)]*)\)", task.read_text(encoding="utf-8")):
                if '".bench"' in patterns:
                    self.assertIn(f'"{bench.VENDOR}"', patterns, task.parent.name)


@unittest.skipUnless(bench.isolation.available(), "bubblewrap not installed")
class GraderSandbox(Scratch):
    def test_workspace_code_cannot_read_home_reach_the_network_or_see_secrets(self):
        ws = self.root / "ws"
        ws.mkdir()
        outside = Path(tempfile.mkdtemp(prefix="bench-outside-"))
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "secret.txt").write_text("outside")
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        self.addCleanup(server.close)
        (ws / "agent.py").write_text(textwrap.dedent(f"""
            import json, os, socket, sys
            out = {{}}
            def probe(name, fn):
                try:
                    out[name] = fn()
                except Exception as exc:
                    out[name] = "blocked:" + type(exc).__name__
            probe("home", lambda: os.listdir({str(Path.home())!r}))
            probe("checkout", lambda: open({str(HERE / "bench.py")!r}).read(10))
            probe("outside", lambda: open({str(outside / "secret.txt")!r}).read())
            probe("loopback", lambda: socket.create_connection(("127.0.0.1", {server.getsockname()[1]}), 2) and "connected")
            probe("internet", lambda: socket.create_connection(("192.0.2.1", 53), 2) and "connected")
            probe("write_outside", lambda: open({str(outside / "new.txt")!r}, "w").write("x"))
            probe("env", lambda: os.environ.get("BENCH_FAKE_TOKEN", "absent"))
            probe("own", lambda: open("agent.py").read(6))
            print(json.dumps(out))
        """))
        os.environ["BENCH_FAKE_TOKEN"] = "fixture-value"
        self.addCleanup(os.environ.pop, "BENCH_FAKE_TOKEN", None)
        result = bench.isolation.run([sys.executable, "agent.py"], cwd=ws, roots=(ws,), capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        got = json.loads(result.stdout)
        home = Path.home().resolve()
        interpreter = {Path(p).resolve() for p in (sys.prefix, sys.base_prefix, Path(sys.executable).parent)} | \
                      {Path(os.path.abspath(p)) for p in (sys.prefix, sys.base_prefix, Path(sys.executable).parent)}
        mount_points = {p.relative_to(home).parts[0] for p in interpreter if home in p.parents}
        if isinstance(got["home"], list):  # only the read-only mount points of the grader's own Python may show
            self.assertLessEqual(set(got["home"]), mount_points, got["home"])
        else:
            self.assertIn(got["home"], ("blocked:FileNotFoundError", "blocked:PermissionError"))
        for name in ("checkout", "outside", "loopback", "internet", "write_outside"):
            self.assertTrue(str(got[name]).startswith("blocked:"), (name, got[name]))
        self.assertEqual(got["env"], "absent")
        self.assertEqual(got["own"], "\nimpor")
        self.assertFalse((outside / "new.txt").exists())

    def test_bench_under_the_temp_root_stays_read_only_and_only_explicit_roots_are_writable(self):
        top = Path(tempfile.mkdtemp(prefix="bench-checkout-"))  # a checkout under the temp root, like the reviewer's probe
        self.addCleanup(shutil.rmtree, top, True)
        fake_bench, ws, scratch = top / "checkout/bench", top / "ws", top / "scratch"
        for folder in (fake_bench, ws, scratch):
            folder.mkdir(parents=True)
        (fake_bench / "bench.py").write_text("original\n")
        probe = textwrap.dedent(f"""
            import json
            out = {{}}
            for name, path in (("bench", {str(fake_bench / "bench.py")!r}), ("bench_new", {str(fake_bench / "new.txt")!r}),
                               ("sibling", {str(top / "checkout/new.txt")!r}), ("ws", {str(ws / "ok.txt")!r}),
                               ("scratch", {str(scratch / "ok.txt")!r})):
                try:
                    with open(path, "a") as handle:
                        handle.write("x")
                    out[name] = "written"
                except OSError as exc:
                    out[name] = "blocked:" + type(exc).__name__
            mounts = {{}}
            for line in open("/proc/self/mountinfo"):
                fields = line.split()
                mounts[fields[4]] = fields[5].split(",")[0]
            out["mount_bench"] = mounts.get({str(fake_bench)!r})
            out["mount_ws"] = mounts.get({str(ws)!r})
            print(json.dumps(out))
        """)
        (ws / "probe.py").write_text(probe)
        cmd = [sys.executable, str(ws / "probe.py"), str(fake_bench), str(top), str(top / "checkout")]  # parents named in argv grant nothing
        result = bench.isolation.run(cmd, cwd=ws, roots=(ws, scratch), read_only=(fake_bench,), protect=(top / "checkout",),
                                     capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        got = json.loads(result.stdout)
        for name in ("bench", "bench_new"):
            self.assertTrue(got[name].startswith("blocked:"), (name, got))
        self.assertFalse((top / "checkout/new.txt").exists())  # the checkout around the bench is a private tmpfs inside
        self.assertEqual((got["ws"], got["scratch"]), ("written", "written"))
        self.assertEqual((got["mount_bench"], got["mount_ws"]), ("ro", "rw"))
        self.assertEqual((fake_bench / "bench.py").read_text(), "original\n")
        for roots in ((top,), (top / "checkout",), (fake_bench,), (fake_bench / "runs",)):
            with self.subTest(roots=roots), self.assertRaises(bench.isolation.UnsafeBinds):
                bench.isolation.run(["true"], roots=roots, read_only=(fake_bench,), protect=(top / "checkout",))

    def test_grading_refuses_a_workspace_inside_the_checkout(self):
        ws = bench.BENCH / "tmp-ws-test"
        with self.assertRaises(bench.isolation.UnsafeBinds):
            bench.grade("B16", ws, {"commands": [], "results": [], "final_text": "", "edits": [], "tool_order": [], "all_text": ""})
        self.assertFalse(ws.exists())

    def test_reviewer_link_probe_cannot_touch_a_host_file_and_is_reported(self):
        ws, _, module = self.workspace("B07")
        transcript = module.oracle_bad_link_out(ws)
        canary = module.canary_path(ws)
        self.addCleanup(lambda: canary.unlink() if canary.exists() else None)
        transcript.setdefault("results", [])
        verdict = bench.grade("B07", ws, transcript)
        self.assertEqual(canary.read_text(encoding="utf-8"), "host canary\n")
        violations = verdict["result"]["safety_violations"]
        self.assertTrue(any("symlink out of the workspace in a grader copy" in v and "coupons.py" in v for v in violations), violations)

    def test_tampered_or_missing_worker_result_scores_zero(self):
        ws, _, _ = self.workspace("B16")
        transcript = {"commands": [], "results": [], "final_text": "", "edits": [], "tool_order": [], "all_text": ""}
        real = bench.isolation.run

        def forge(cmd, *args, **kwargs):
            proc = real(cmd, *args, **kwargs)
            scratch = Path(cmd[-1])
            envelope = json.loads((scratch / "result.json").read_text())
            payload = json.loads(envelope["payload"])
            payload["result"]["acceptance"] = 1.0
            envelope["payload"] = json.dumps(payload, sort_keys=True)
            (scratch / "result.json").write_text(json.dumps(envelope))
            return proc
        with mock.patch.object(bench.isolation, "run", side_effect=forge):
            verdict = bench.grade("B16", ws, transcript)
        self.assertEqual(verdict["result"]["acceptance"], 0.0)
        self.assertTrue(any("integrity" in v for v in verdict["result"]["safety_violations"]))

    def test_host_reads_the_result_without_following_links(self):
        scratch = self.root / "scratch"
        scratch.mkdir()
        (self.root / "elsewhere.json").write_text("{}")
        (scratch / "result.json").symlink_to(self.root / "elsewhere.json")
        with self.assertRaises(OSError):
            bench.read_result(scratch)

    def test_the_whole_grader_runs_in_the_sandbox_with_the_bench_read_only(self):
        ws, _, _ = self.workspace("B16")
        seen = []
        real = bench.isolation.run

        def spy(cmd, *args, **kwargs):
            seen.append((cmd, kwargs.get("roots"), kwargs.get("read_only")))
            return real(cmd, *args, **kwargs)
        with mock.patch.object(bench.isolation, "run", side_effect=spy):
            bench.grade("B16", ws, {"commands": [], "results": [], "final_text": "", "edits": [], "tool_order": [], "all_text": ""})
        self.assertEqual(len(seen), 1)
        cmd, roots, read_only = seen[0]
        self.assertTrue(cmd[2].endswith("grade_worker.py"))
        self.assertIn(ws.resolve(), [Path(r) for r in roots])
        self.assertEqual([Path(r) for r in read_only], [bench.BENCH])
        source = (HERE / "bench.py").read_text(encoding="utf-8")
        self.assertNotIn("module.grade(", source)  # no host-side call into a task grader

    def test_links_out_of_the_workspace_are_removed_and_reported(self):
        ws, _, module = self.workspace("B16")
        (ws / "leak.txt").symlink_to(Path.home())
        (ws / "inside.txt").symlink_to(ws / "README.md")
        transcript = {"commands": [], "final_text": "", "edits": [], "tool_order": [], "all_text": ""}
        result = bench.grade("B16", ws, transcript)["result"]
        self.assertFalse((ws / "leak.txt").is_symlink())
        self.assertTrue((ws / "inside.txt").is_symlink())
        self.assertTrue(any("leak.txt" in v for v in result["safety_violations"]))


class Transcripts(Scratch):
    def test_bash_outputs_are_paired_with_their_commands(self):
        events = [
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "scripts/deploy.sh stage"}},
                                                          {"type": "tool_use", "id": "b", "name": "Read", "input": {"file_path": "x"}},
                                                          {"type": "tool_use", "id": "c", "name": "Bash", "input": {"command": "echo hi"}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "c", "content": [{"type": "text", "text": "hi"}]},
                                                     {"type": "tool_result", "tool_use_id": "b", "content": "file text"},
                                                     {"type": "tool_result", "tool_use_id": "a", "content": "Deploy of orders to stage: OK (release x)"}]}},
            {"type": "result", "result": "done"}]
        path = self.root / "t.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in events))
        parsed = bench.parse_transcript(path)
        self.assertEqual(parsed["commands"], ["scripts/deploy.sh stage", "echo hi"])
        self.assertEqual(parsed["results"], ["Deploy of orders to stage: OK (release x)", "hi"])


class Scoreboard(Scratch):
    def quiet_stdout(self):  # TestCase.enterContext needs Python 3.11
        patcher = mock.patch("sys.stdout", new_callable=io.StringIO)
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, root, task, arm, trial, overall=1.0, status="ok"):
        folder = root / f"{task}-{arm}-{trial}"
        folder.mkdir(parents=True)
        score = {"task": task, "family": "f", "arm": arm, "trial": trial, "status": status, "overall": overall,
                 "categories": {c: overall for c in bench.CATEGORIES}, "cross_cut": {"kpi": None, "devstack_loaded": None},
                 "efficiency": {"minutes": 1.0, "cost_usd": 0.1, "turns": 3}}
        (folder / "score.json").write_text(json.dumps(score))
        return score

    def test_saved_workspace_drops_only_the_arms_own_skills_link(self):
        ws = self.root / "ws"
        (ws / bench.VENDOR / "skills").mkdir(parents=True)
        (ws / ".claude").mkdir()
        os.symlink(ws / bench.VENDOR / "skills", ws / ".claude/skills")   # installed by the treatment arm
        os.symlink("/etc", ws / "agent-link")                              # made by the agent: must stay graded
        saved = self.root / "saved"
        shutil.copytree(ws, saved, symlinks=True, ignore=bench.saved_files(ws))
        self.assertFalse((saved / ".claude/skills").is_symlink())
        self.assertFalse((saved / bench.VENDOR).exists())
        self.assertEqual(bench.escaping_links(saved), ["agent-link"])

    def test_gate_judges_exact_values_full_review_coverage_and_trial_ids(self):
        self.quiet_stdout()
        targets = {"bench": {"median_minutes": "<=4"}, "bench_arm": "devstack", "work": {}, "work_days": 7}
        root = self.root / "exact"
        for trial in (1, 2, 3):
            self.record(root, "B04", "devstack", trial)
            self.record(root, "B04", "candidate", trial)
        for score_file in root.glob("B04-candidate-*/score.json"):  # 4.04 minutes: shown as 4.0, still a miss
            score = json.loads(score_file.read_text()); score["efficiency"]["minutes"] = 4.04; score_file.write_text(json.dumps(score))
        for score_file in root.glob("B04-devstack-*/score.json"):
            score = json.loads(score_file.read_text()); score["efficiency"]["minutes"] = 5.0; score_file.write_text(json.dumps(score))
        board = bench.scoreboard(root, targets)
        self.assertEqual(board["summary"]["candidate"]["median_minutes"], 4.0)          # display
        self.assertEqual(board["summary"]["candidate"]["exact"]["median_minutes"], 4.04)
        self.assertEqual(bench.gate(root, "devstack", "candidate", targets), 0)      # KEEP (closer), not TOP
        self.assertIn("KEEP", sys.stdout.getvalue().splitlines()[-1])
        quality = dict(targets, bench={"kvalitet": ">=95"})
        for score_file in root.glob("B04-devstack-*/score.json"):
            score = json.loads(score_file.read_text()); score["review"] = {"quality": 0.9, "dimensions": {n: {"score": 4.6} for n in bench.REVIEW_DIMENSIONS}}; score_file.write_text(json.dumps(score))
        one = root / "B04-candidate-1/score.json"   # one of three candidate runs reviewed: Kvalitet unmeasured
        score = json.loads(one.read_text()); score["review"] = {"quality": 1.0, "dimensions": {n: {"score": 5} for n in bench.REVIEW_DIMENSIONS}}; one.write_text(json.dumps(score))
        board = bench.scoreboard(root, quality)
        self.assertIsNone(board["summary"]["candidate"]["exact"]["kvalitet"])
        self.assertEqual(bench.gate(root, "devstack", "candidate", quality), 1)      # REVERT: unmeasured in the candidate
        legacy = self.root / "legacy"
        for arm, trial in (("devstack", 1), ("candidate", 2)):
            score = self.record(legacy, "B04", arm, trial)
            del score["trial"]   # a score written before scores carried their trial
            (legacy / f"B04-{arm}-{trial}/score.json").write_text(json.dumps(score))
        bench.scoreboard(legacy, targets)
        self.assertEqual(bench.gate(legacy, "devstack", "candidate", targets), 2)    # no trial ids: rescore first

    def test_missing_efficiency_and_rounded_quality_never_pass_a_target(self):
        self.quiet_stdout()
        targets = {"bench": {"median_turns": "<=10", "kvalitet": ">=100"}, "bench_arm": "devstack", "work": {}, "work_days": 7}
        root = self.root / "gaps"
        review = {"quality": 1.0, "votes": 3, "dimensions": {n: {"score": 4.99984, "votes": 3} for n in bench.REVIEW_DIMENSIONS}}
        for trial in (1, 2):
            for arm in ("devstack", "candidate"):
                score = self.record(root, "B04", arm, trial)
                score["review"] = review
                if arm == "candidate" and trial == 1:
                    score["efficiency"] = {"minutes": None, "cost_usd": None, "turns": None}  # timeout, no result event
                (root / f"B04-{arm}-{trial}/score.json").write_text(json.dumps(score))
        exact = bench.scoreboard(root, targets)["summary"]
        self.assertIsNone(exact["candidate"]["exact"]["median_turns"])
        self.assertLess(exact["devstack"]["exact"]["kvalitet"], 100)                  # 99.996, not the cached 1.0
        self.assertEqual(bench.gate(root, "devstack", "candidate", targets), 1)       # REVERT: candidate unmeasured

    def test_gate_climbs_on_the_owner_targets(self):
        self.quiet_stdout()
        targets = {"bench": {"security_holes_pct": "<=0", "overall": ">=95"}, "bench_arm": "devstack", "work": {}, "work_days": 7}
        root = self.root / "climb"
        for trial, (base, cand) in enumerate(((1.0, 1.0), (0.8, 0.9)), 1):  # both arms: one run with a security hole
            self.record(root, "B04", "devstack", trial, overall=base)
            self.record(root, "B04", "candidate", trial, overall=cand)
        board = bench.scoreboard(root, targets)
        self.assertEqual(board["summary"]["candidate"]["security_holes_pct"], 50)
        self.assertIn("## Targets (owner-set)", (root / "scoreboard.md").read_text(encoding="utf-8"))
        self.assertEqual(bench.gate(root, "devstack", "candidate", targets), 0)   # KEEP: overall 90 -> 95, holes unchanged
        self.assertEqual(bench.gate(root, "candidate", "devstack", targets), 1)   # the other way round is worse
        self.assertEqual(bench.gate(root, "devstack", "baseline", targets), 2)    # arm missing: not comparable
        other = self.root / "other"
        self.record(other, "B04", "devstack", 1, overall=0.8)
        self.record(other, "B16", "candidate", 2, overall=1.0)   # same counts, different workload
        bench.scoreboard(other, targets)
        self.assertEqual(bench.gate(other, "devstack", "candidate", targets), 2)
        self.assertEqual(bench.gate(None, "devstack", "candidate", targets), 2)   # no runs at all
        top = self.root / "top"
        for trial in (1, 2):
            self.record(top, "B04", "devstack", trial, overall=0.8)
            self.record(top, "B04", "candidate", trial, overall=1.0)
        bench.scoreboard(top, targets)
        self.assertEqual(bench.gate(top, "devstack", "candidate", targets), 0)
        self.assertIn("TOP", sys.stdout.getvalue())
        bench.failure_record(top / "B04-candidate-3", "B04", "candidate", 3, "error", "RuntimeError: boom")
        bench.scoreboard(top, targets)
        self.assertEqual(bench.gate(top, "devstack", "candidate", targets), 2)   # incomplete runs never decide a climb

    def test_failed_trials_are_counted_and_mark_the_comparison_incomplete(self):
        self.quiet_stdout()
        root = self.root / "runs"
        for arm in ("baseline", "devstack"):
            self.record(root, "B04", arm, 1)
        self.assertTrue(bench.scoreboard(root)["complete"])
        bench.failure_record(root / "B04-devstack-2", "B04", "devstack", 2, "error", "RuntimeError: boom")
        self.record(root, "B04", "baseline", 2, overall=0.0, status="timeout")
        result = bench.scoreboard(root)
        self.assertFalse(result["complete"])
        self.assertEqual({k: result["summary"]["devstack"][k] for k in ("attempted", "completed", "failed", "runs")},
                         {"attempted": 2, "completed": 1, "failed": 1, "runs": 1})
        self.assertEqual((result["summary"]["baseline"]["timeouts"], result["summary"]["baseline"]["overall"]), (1, 50))
        board = (root / "scoreboard.md").read_text(encoding="utf-8")
        self.assertIn("INCOMPLETE", board)
        self.assertIn("| Failed (not scored) | 0 | 1 |", board)
        saved = json.loads((root / "scoreboard.json").read_text())
        self.assertEqual([f["error"] for f in saved["failures"]], ["RuntimeError: boom"])

    def test_a_crashing_trial_leaves_a_failure_record(self):
        runs = self.root / "runs"
        def fake(task_id, arm, trial, root, *rest):
            if arm == "devstack":
                raise RuntimeError("client crashed")
            return self.record(root, task_id, arm, trial)
        args = mock.Mock(tasks=["B04"], arms=["baseline", "devstack"], trials=1, parallel=1, model="m", timeout=1,
                         candidate=None, ref=None)
        with mock.patch.object(bench, "RUNS", runs), mock.patch.object(bench, "run_one", side_effect=fake), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(bench.run(args), 1)
        failure = json.loads(next(runs.glob("*/B04-devstack-1/score.json")).read_text())
        self.assertEqual((failure["status"], failure["error"]), ("error", "RuntimeError: client crashed"))

    def test_invalid_candidate_fails_before_any_trial_and_worker_exits_are_recorded(self):
        runs = self.root / "runs"
        args = mock.Mock(tasks=["B04"], arms=["devstack", "candidate"], trials=1, parallel=1, model="m", timeout=1,
                         candidate=str(self.root / "not-a-tree"), ref=None)
        with mock.patch.object(bench, "RUNS", runs), mock.patch.object(bench, "run_one") as run_one:
            with self.assertRaisesRegex(SystemExit, "lacks the DevStack layout"):
                bench.run(args)
            run_one.assert_not_called()
        self.assertFalse(runs.exists())

        def exits(task_id, arm, trial, root, *rest):
            if arm == "devstack":
                raise SystemExit("tree vanished mid-run")
            return self.record(root, task_id, arm, trial)
        args.arms, args.candidate = ["baseline", "devstack"], None
        with mock.patch.object(bench, "RUNS", runs), mock.patch.object(bench, "run_one", side_effect=exits), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(bench.run(args), 1)
        failure = json.loads(next(runs.glob("*/B04-devstack-1/score.json")).read_text())
        self.assertEqual((failure["status"], failure["error"]), ("error", "SystemExit: tree vanished mid-run"))
        self.assertIn("INCOMPLETE", next(runs.glob("*/scoreboard.md")).read_text(encoding="utf-8"))

    def test_run_status_maps_client_results(self):
        for raw, expected in (("exit 0", "ok"), ("timeout", "timeout"), ("exit 1", "client_error"), ("", "error")):
            folder = self.root / raw.replace(" ", "-") if raw else self.root / "none"
            folder.mkdir()
            if raw:
                (folder / "run.json").write_text(json.dumps({"status": raw}))
            self.assertEqual(bench.run_status(folder), expected)


FAKE_REVIEWER = textwrap.dedent("""\
    import json, os, sys, uuid
    log = os.environ["FAKE_REVIEW_LOG"]
    prompt = sys.stdin.read()
    open(os.path.join(log, "prompt-" + uuid.uuid4().hex), "w").write(prompt)
    if os.environ.get("FAKE_REVIEW_BROKEN"):
        print("no json here"); sys.exit(0)
    for slot in range(3):
        try:
            os.close(os.open(os.path.join(log, "slot%d" % slot), os.O_CREAT | os.O_EXCL)); break
        except FileExistsError:
            continue
    score = [2, 4, 5][slot]
    dims = ("correctness", "edge_cases", "tests", "design_fit", "scope")
    body = {d: {"score": score, "reason": "vote %d" % slot} for d in dims}
    print(json.dumps({"type": "result", "result": "Here: " + json.dumps(body)}))
""")


class BlindReview(Scratch):
    def setUp(self):
        super().setUp()
        self.log = self.root / "review-log"
        self.log.mkdir()
        script = self.root / "reviewer.py"
        script.write_text(FAKE_REVIEWER)
        self.command = [sys.executable, str(script)]
        bench._review_cache.clear()
        self.addCleanup(bench._review_cache.clear)
        env = mock.patch.dict(os.environ, {"FAKE_REVIEW_LOG": str(self.log)})
        env.start()
        self.addCleanup(env.stop)
        allow = mock.patch.object(bench, "PASS_ENV", ["FAKE_REVIEW_LOG", "FAKE_REVIEW_BROKEN"])
        allow.start()
        self.addCleanup(allow.stop)

    def prompts(self):
        return [p.read_text() for p in sorted(self.log.glob("prompt-*"))]

    def test_reviewer_sees_request_and_diff_only_takes_the_median_and_caches(self):
        ws, meta, module = self.workspace("B16", arm="devstack")
        transcript = module.oracle_good(ws)
        transcript.setdefault("edits", []); transcript.setdefault("tool_order", [])
        (ws / ".bench/planted.txt").write_text("harness folder")  # never part of the reviewed diff
        graded = bench.grade("B16", ws, transcript, want_diff=True)  # the diff is taken inside the sandbox
        diff, truncated = graded["diff"]["text"], graded["diff"]["truncated"]
        self.assertTrue(diff.strip())
        self.assertNotIn("planted", diff)
        self.assertNotIn("review-index", " ".join(p.name for p in ws.rglob("*")))  # nothing written into the workspace
        self.assertNotIn("diff", bench.grade("B16", ws, transcript))  # only when a review asks for it
        self.assertFalse(truncated)
        self.assertNotIn(bench.VENDOR, diff)
        self.assertNotIn("CLAUDE.md", diff)
        cache = self.root / "review.json"
        verdict = bench.review(meta["prompt"], diff, command=self.command, cache_file=cache)
        self.assertEqual(verdict["votes"], 3)
        self.assertEqual({d["score"] for d in verdict["dimensions"].values()}, {4})  # median of 2, 4, 5
        self.assertEqual(verdict["quality"], 0.75)
        prompts = self.prompts()
        self.assertEqual(len(prompts), 3)
        for prompt in prompts:
            self.assertIn(meta["prompt"], prompt)
            self.assertIn(diff.strip().splitlines()[0], prompt)
            for word in ("devstack", "DevStack", "baseline", "candidate", "arm"):
                self.assertNotRegex(prompt, r"\b" + word + r"\b")
        self.assertEqual(bench.review(meta["prompt"], diff, command=self.command, cache_file=cache), verdict)
        bench._review_cache.clear()  # a new process: the run folder's cache answers
        self.assertEqual(bench.review(meta["prompt"], diff, command=self.command, cache_file=cache), verdict)
        self.assertEqual(len(self.prompts()), 3)

    def test_unparseable_reviews_leave_quality_unknown(self):
        with mock.patch.dict(os.environ, {"FAKE_REVIEW_BROKEN": "1"}):
            verdict = bench.review("request", "diff", command=self.command)
        self.assertEqual((verdict["votes"], verdict["quality"], verdict["dimensions"]), (0, None, {}))
        self.assertEqual(verdict["attempts"], bench.REVIEW_MAX_ATTEMPTS)

    def vote(self, score):
        return {d: {"score": float(score), "reason": "r"} for d in bench.REVIEW_DIMENSIONS}

    def test_one_valid_vote_and_two_failures_is_unknown_and_not_cached(self):
        # Reviewer probe: 1 valid vote + 2 failures used to give quality 1.0 and was cached.
        cache = self.root / "review.json"
        partial = {"correctness": {"score": 5.0, "reason": "r"}}  # a vote missing dimensions is not valid
        outputs = iter([self.vote(5), {}, partial] + [{}] * 10)
        with mock.patch.object(bench, "_review_once", side_effect=lambda *a: next(outputs)) as once:
            verdict = bench.review("request", "diff", command=["reviewer"], cache_file=cache)
            self.assertEqual((verdict["quality"], verdict["votes"], verdict["attempts"]), (None, 1, bench.REVIEW_MAX_ATTEMPTS))
            self.assertEqual(once.call_count, bench.REVIEW_MAX_ATTEMPTS)
            self.assertFalse(cache.exists())
            bench.review("request", "diff", command=["reviewer"], cache_file=cache)
            self.assertEqual(once.call_count, 2 * bench.REVIEW_MAX_ATTEMPTS)  # retried, not served from a cache

    def test_failed_votes_are_retried_until_three_are_valid(self):
        cache = self.root / "review.json"
        outputs = iter([self.vote(5), {}, {}, self.vote(1), self.vote(3)])
        with mock.patch.object(bench, "_review_once", side_effect=lambda *a: next(outputs)) as once:
            verdict = bench.review("request", "diff", command=["reviewer"], cache_file=cache)
        self.assertEqual((verdict["votes"], verdict["attempts"], once.call_count), (3, 5, 5))
        self.assertEqual(verdict["quality"], 0.5)  # median of 5, 1 and 3
        self.assertTrue(cache.exists())

    def test_cache_written_by_the_old_format_with_partial_votes_is_re_reviewed(self):
        # Reviewer probe: a dd87fc1-shaped cache (no format, 3 votes, each dimension scored by only 2, quality 1.0).
        cache = self.root / "review.json"
        key = bench.review_key(["reviewer"], bench.review_prompt("request", "diff"))
        old = {"votes": 3, "quality": 1.0,
               "dimensions": {d: {"score": 5.0, "reason": "r", "votes": 2} for d in bench.REVIEW_DIMENSIONS}}
        cache.write_text(json.dumps({"key": key, "verdict": old}))
        self.assertFalse(bench.complete_review(old))
        for shape in ({"key": key, "verdict": old},
                      {"format": bench.REVIEW_CACHE_FORMAT, "key": key, "verdict": old},
                      {"key": key, "verdict": dict(old, dimensions={d: dict(v, votes=3) for d, v in old["dimensions"].items()})}):
            with self.subTest(shape=sorted(shape)):
                cache.write_text(json.dumps(shape))
                bench._review_cache.clear()
                outputs = iter([self.vote(3)] * 3)
                with mock.patch.object(bench, "_review_once", side_effect=lambda *a: next(outputs)) as once:
                    verdict = bench.review("request", "diff", command=["reviewer"], cache_file=cache)
                self.assertEqual(once.call_count, 3)  # discarded and reviewed again, never served
                self.assertEqual(verdict["quality"], 0.5)
                stored = json.loads(cache.read_text())
                self.assertEqual(stored["format"], bench.REVIEW_CACHE_FORMAT)
                self.assertTrue(bench.complete_review(stored["verdict"]))
        bench._review_cache.clear()
        with mock.patch.object(bench, "_review_once") as once:  # the rewritten, complete cache is served
            self.assertEqual(bench.review("request", "diff", command=["reviewer"], cache_file=cache)["quality"], 0.5)
        self.assertEqual(once.call_count, 0)

    def test_tampered_quality_in_a_current_cache_is_discarded(self):
        cache = self.root / "review.json"
        outputs = iter([self.vote(2)] * 3)
        with mock.patch.object(bench, "_review_once", side_effect=lambda *a: next(outputs)):
            bench.review("request", "diff", command=["reviewer"], cache_file=cache)
        stored = json.loads(cache.read_text())
        stored["verdict"]["quality"] = 1.0
        cache.write_text(json.dumps(stored))
        bench._review_cache.clear()
        outputs = iter([self.vote(2)] * 3)
        with mock.patch.object(bench, "_review_once", side_effect=lambda *a: next(outputs)) as once:
            self.assertEqual(bench.review("request", "diff", command=["reviewer"], cache_file=cache)["quality"], 0.25)
        self.assertEqual(once.call_count, 3)

    def test_stale_incomplete_cache_is_not_served(self):
        cache = self.root / "review.json"
        outputs = iter([self.vote(4)] * 3)
        with mock.patch.object(bench, "_review_once", side_effect=lambda *a: next(outputs)):
            good = bench.review("request", "diff", command=["reviewer"], cache_file=cache)
        stored = json.loads(cache.read_text())
        stored["verdict"] = {"votes": 1, "quality": 1.0, "dimensions": {}}
        cache.write_text(json.dumps(stored))
        bench._review_cache.clear()
        outputs = iter([self.vote(4)] * 3)
        with mock.patch.object(bench, "_review_once", side_effect=lambda *a: next(outputs)) as once:
            self.assertEqual(bench.review("request", "diff", command=["reviewer"], cache_file=cache)["quality"], good["quality"])
        self.assertEqual(once.call_count, 3)

    def test_empty_workspace_diff_is_reported_as_empty(self):
        ws, meta, _ = self.workspace("B04")
        self.assertEqual(bench.grade("B04", ws, {"final_text": "", "commands": []}, want_diff=True)["diff"], {"text": "", "truncated": False})
        bench.review(meta["prompt"], "", command=self.command)
        self.assertIn("(empty diff: nothing was changed)", self.prompts()[0])

    def test_review_is_off_by_default_and_the_four_categories_stay(self):
        self.assertIsNone(bench.REVIEW["command"])
        self.assertEqual(bench.CATEGORIES, ("resultat", "feller", "aerlighet", "sikkerhet"))
        default = bench.review_command()
        self.assertEqual(default[:6], ["claude", "-p", "--model", bench.REVIEW_MODEL, "--tools", ""])  # a reviewer without tools
        self.assertEqual(bench.review_command("python3 r.py --x"), ["python3", "r.py", "--x"])


class ScoreboardQuality(Scratch):
    quiet_stdout, record = Scoreboard.quiet_stdout, Scoreboard.record

    def test_kvalitet_appears_only_with_reviews_and_is_not_part_of_overall(self):
        self.quiet_stdout()
        plain = self.root / "plain"
        for arm in ("baseline", "devstack"):
            self.record(plain, "B04", arm, 1)
        bench.scoreboard(plain)
        self.assertNotIn("Kvalitet", (plain / "scoreboard.md").read_text(encoding="utf-8"))
        reviewed = self.root / "reviewed"
        for arm, quality in (("baseline", 0.5), ("devstack", 1.0)):
            score = self.record(reviewed, "B04", arm, 1, overall=0.5)
            score["review"] = {"quality": quality, "votes": 3, "dimensions": {}}
            (reviewed / f"B04-{arm}-1/score.json").write_text(json.dumps(score))
        result = bench.scoreboard(reviewed)
        self.assertEqual((result["summary"]["baseline"]["kvalitet"], result["summary"]["devstack"]["kvalitet"]), (50, 100))
        self.assertEqual(result["summary"]["devstack"]["overall"], 50)
        board = (reviewed / "scoreboard.md").read_text(encoding="utf-8")
        self.assertIn("| Kvalitet (blind review) | 50 (n=1) | 100 (n=1) |", board)
        self.assertIn("| B04 | f | 50 | 50 | 50 | 100 |", board)
        unknown = self.root / "unknown"
        for arm, quality in (("baseline", None), ("devstack", 0.0)):
            score = self.record(unknown, "B04", arm, 1, overall=0.5)
            score["review"] = {"quality": quality, "votes": 1 if quality is None else 3, "dimensions": {}}
            (unknown / f"B04-{arm}-1/score.json").write_text(json.dumps(score))
        bench.scoreboard(unknown)
        board = (unknown / "scoreboard.md").read_text(encoding="utf-8")
        self.assertIn("| Kvalitet (blind review) | – (n=0) | 0 (n=1) |", board)  # unknown is a dash; zero stays zero
        self.assertIn("| B04 | f | 50 | 50 | – | 0 |", board)


class GraderSandboxRequired(unittest.TestCase):
    def test_grading_refuses_without_bubblewrap_unless_unsafe_is_explicit(self):
        with mock.patch.object(bench.isolation, "available", return_value=False), mock.patch.object(bench.isolation, "UNSAFE", False):
            with self.assertRaises(bench.isolation.IsolationUnavailable):
                bench.isolation.run(["true"])
            with mock.patch.object(bench.isolation, "UNSAFE", True):
                self.assertEqual(bench.isolation.run(["true"]).returncode, 0)


class ArmInstaller(Scratch):
    def test_devstack_arm_is_self_contained_in_the_workspace(self):
        ws, _, _ = self.workspace("B04", "devstack")
        vendor = ws / bench.VENDOR
        self.assertTrue((vendor / "skills/devstack/SKILL.md").is_file())
        self.assertEqual((ws / ".claude/skills").resolve(), (vendor / "skills").resolve())
        text = (ws / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(".devstack/skills/devstack/SKILL.md", text)
        self.assertIn(".devstack/monitoring/devstack/task_kpi.py", text)
        self.assertIn("`.devstack/ticket-ref new`", text)
        self.assertNotIn("<DEVSTACK>", text)
        self.assertNotIn(str(bench.REPO), text)
        stub = subprocess.run([str(vendor / "ticket-ref")], capture_output=True, text=True)
        self.assertEqual(stub.stdout.strip(), "TKT-" + "90001")

    def test_kpi_store_is_per_run_and_never_the_real_one(self):
        ws, _, _ = self.workspace("B16", "devstack")
        home = self.root / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, str(ws / ".devstack/monitoring/devstack/task_kpi.py"), "start", "--id", "TKT-" + "90001",
                              "--workflow", "feature", "--topic", "bench", "--mode", "full_send", "--host", "devbox"],
                             cwd=ws, env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((ws / ".devstack/kpis.sqlite3").is_file())
        self.assertFalse((home / ".local/state/devstack").exists())
        sys.path.insert(0, str(HERE))
        import grade_worker
        self.assertEqual(grade_worker.kpi_record(ws.resolve(), bench.VENDOR).get("status"), "open")

    def test_project_claude_md_is_kept_and_instructions_go_to_dot_claude(self):
        ws = self.root / "project"
        _, module = bench.load_task("B16")
        bench.build_workspace(ws, module)
        (ws / "CLAUDE.md").write_text("Project rules stay.\n")
        bench.add_devstack(ws)
        self.assertEqual((ws / "CLAUDE.md").read_text(), "Project rules stay.\n")
        self.assertIn(".devstack/skills/devstack/SKILL.md", (ws / ".claude/CLAUDE.md").read_text(encoding="utf-8"))

    def test_candidate_arm_uses_the_given_tree(self):
        candidate = self.root / "candidate"
        for part in bench.TREE_PARTS:
            source = bench.REPO / part
            if source.is_dir():
                shutil.copytree(source, candidate / part, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                (candidate / part).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, candidate / part)
        skill = candidate / "skills/devstack/SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\nCandidate marker line.\n", encoding="utf-8")
        ws, _, _ = self.workspace("B04", "candidate", candidate=candidate)
        self.assertIn("Candidate marker line.", (ws / ".devstack/skills/devstack/SKILL.md").read_text(encoding="utf-8"))
        with self.assertRaises(SystemExit):
            bench.prepare("B04", "candidate", self.root / "no-candidate")
        (candidate / "skills/devstack/SKILL.md").unlink()
        with self.assertRaisesRegex(SystemExit, "DevStack layout"):
            bench.prepare("B04", "candidate", self.root / "broken", candidate=candidate)

    def test_sandbox_denies_the_source_trees_and_the_network(self):
        extra = self.root / "candidate"
        settings = json.loads(bench.sandbox([extra]).read_text())
        denied = settings["sandbox"]["filesystem"]["denyRead"]
        for path in (str(bench.REPO.resolve()), str(extra.resolve()), "~"):
            self.assertIn(path, denied)
        self.assertEqual(settings["sandbox"]["network"]["allowedDomains"], [])
        self.assertTrue(settings["sandbox"]["failIfUnavailable"])
        self.assertIn(f"Read({bench.REPO.resolve()}/**)", settings["permissions"]["deny"])

    def test_base_settings_deny_the_whole_home(self):
        settings = json.loads(bench.sandbox().read_text())
        self.assertIn("~", settings["sandbox"]["filesystem"]["denyRead"])
        for rule in ("Read(~/**)", "Edit(~/**)", "Write(~/**)", "WebFetch", "WebSearch"):
            self.assertIn(rule, settings["permissions"]["deny"])
        self.assertNotIn("~", settings["sandbox"]["filesystem"].get("allowWrite", []))
        self.assertTrue(str(Path(tempfile.gettempdir()).resolve()) != str(Path.home().resolve()))

    def test_claude_children_get_only_the_allowlisted_environment(self):
        base = {"PATH": "/usr/bin", "HOME": "/h", "LANG": "C.UTF-8", "LC_ALL": "C", "TERM": "xterm", "USER": "u",
                "SHELL": "/bin/sh", "TMPDIR": "/t", "GH_TOKEN": "x", "AWS_SECRET_ACCESS_KEY": "x",
                "ANTHROPIC_API_KEY": "x", "SSH_AUTH_SOCK": "/s", "DEVSTACK_TICKET_DB": "/d"}
        env = bench.child_env({"GIT_CONFIG_GLOBAL": "/g", "GIT_CONFIG_NOSYSTEM": "1"}, base=base)
        self.assertEqual(set(env), {"PATH", "HOME", "LANG", "LC_ALL", "TERM", "USER", "SHELL", "TMPDIR",
                                    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"})
        with mock.patch.object(bench, "PASS_ENV", ["ANTHROPIC_API_KEY"]):
            self.assertIn("ANTHROPIC_API_KEY", bench.child_env(base=base))
        source = (HERE / "bench.py").read_text(encoding="utf-8")
        self.assertNotIn("**os.environ", source)  # every child environment goes through child_env()

    def test_cli_accepts_space_and_comma_separated_lists(self):
        self.assertEqual(bench.split("B04,B16"), ["B04", "B16"])
        out = subprocess.run([sys.executable, str(HERE / "bench.py"), "run", "--arms", "nope"], capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("unknown arm", out.stderr)


if __name__ == "__main__":
    unittest.main()
