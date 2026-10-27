# Runtime coordination adapter

Load for a designated task, resume, delegation or delivery. SessionStart registers the actual session only. Discussion/research/casual testing creates no development ticket. Existing tasks retain their number and ownership. Use the current host's `~/.local/bin/agent-work`; [coordination/README.md](../../../coordination/README.md) is the exact command schema. Read the chosen operation there before mutation.

## Enter and own

1. Use the hook actor or `register` with actual runtime, native session, role and model. Claude uses `AGENT_WORK_NATIVE_SESSION`; Codex its actual native session. Native session and T3 thread IDs differ. Never invent identities or change actors to bypass a gate.
2. Read assigned `show`/`packet`, relevant project `list` and actor `inbox`. Resume the existing task; a named TKT is not a new root. Read later steering; `ack_context` acknowledges changed requirements.
3. Only a designated new development task gets one `create` root: canonical project, title, acceptance, kind, customer/area and exact write scopes. Set work_type, priority, mode/context, PR and deploy target through supported fields. Urgent = outage/blocked users; high = blocking others/near delivery; normal = regular; low = cleanup. Genuine local tools/analysis use deploy_target none with a reason, never as a delivery bypass.
4. Claim before writing with current revision. On CAS/stale revision reread, never edit registry storage. A coordinating parent owns no code; children own non-overlapping canonical paths across worktrees. Expired ownership does not authorize takeover.
5. Checkpoint milestones, compaction/handoff and every 15 active minutes: summary, next_action, precise evidence, pinned workflow/spec, head/base/release, mode, child/watch IDs and cumulative repair history. See [task state](task-state.md).

Mutations use JSON on stdin, not shell-interpolated user text. Example, replacing all placeholders with actual values:

```bash
~/.local/bin/agent-work request <<'JSON'
{"op":"checkpoint","actor":"ACTUAL-ACTOR","id":"ACTUAL-TASK","revision":42,"summary":"Actual finding","next_action":"Concrete next step","evidence":["/actual/evidence"]}
JSON
```

GitHub owns the accepted product spec/delivery visibility; agent-work owns runtime ownership, blockers and execution records. Plans, PM case files and private KPI cache are evidence, not competing editable status. Push/tests/review/deploy are events on the same task.

## Delegate and communicate

Actual Opus 5.5 or Sol 6.1 leads assess the whole goal, dependencies, risk and assignment. Read [MODEL_RANKING.md](../../../MODEL_RANKING.md). Small work stays direct. One child layer; children start no agents/top-level chats.

Execution children follow record_spec → fresh provider_packet → child_run reservation/spawned binding → actual native delegate_task/spawn → child register/claim. Coordinator routes use dispatch_spec. Honor capacity/deferred state and actual provider/model, without silent substitution. A direct lead-owned slice uses supported direct claim, not a forged child identity. Read current required fields from the command reference.

Brief each child with parent/task, goal, actual project/worktree, accessible versioned spec, scope ownership, provider/model/runtime/reasoning, allowed actions, dependencies, acceptance, proof and stop conditions. Tell workers they share the codebase and must preserve other edits. Review independence covers the actual candidate and incremental changes.

Native child results/messages carry findings. Every fresh T3 review round uses delegate_task again with previous findings/responses; backing child thread IDs do not start independent review rounds. Native PR/run events handle waits. For ordinary sessions, steering affects active work; queued means pending, not delivered. Inspect ambiguous outcomes before retrying; preserve idempotency keys and run IDs.

Cross-host transport: `~/.local/bin/peer`, backed by `tools/peer/peer.py` and sibling windows_peer.py. Claude bridge: `tools/codex-claude-bridge/claude_bridge.mjs`. Check --help and actual host/runtime before use. Transport grants no external-message/deploy authority. Keep secrets/private browser/vault records out of briefs/registers.

## T3 Code tools

When running inside T3 Code, prefer its exposed native tools for supported operations. Read the current tool schema and injected runtime contract; names may carry an MCP prefix and capabilities vary by host. Discover relevant deferred tools before declaring them unavailable. Use a supported CLI/connector fallback when the native capability is absent, unsupported or fails under its documented fallback rule; record the actual limit. A role, shared file or model name proves no tool access.

| Operation | Native route |
|---|---|
| Choose models and delegate | `orchestrator_capabilities` for actual provider/model/options, then `delegate_task` for T3-owned or cross-provider children. Retain task/run IDs and use `task_status` when the result is needed; async completion wakes the parent. Each fresh review round is a new delegation with prior findings and responses, using a distinct `clientRequestId` stable across retries. Never continue a review round through `t3_thread_send` to its backing child thread. Same-provider native subagents remain valid when they support the selected model and satisfy the current runtime contract. |
| Resume sessions and bind workspaces | Use exposed `t3_thread_list`/`t3_thread_read` and `t3_worktree_list` rather than client-database access. `t3_thread_send` steering and queued delivery have different states. Only an explicitly requested new top-level conversation uses `t3_thread_launch`/`create_threads`; choose its workspace in the launch tool, not by asking it to `cd`. |
| Work on PRs | `link_pull_request` immediately for each PR created or worked on, including every stack layer. Before handoff use `list_thread_pull_requests` and link any missing PR from this work. Handle current checks and existing comments before the lead calls `watch_pull_request` and ends the turn while work is pending; only comments posted after the watch starts trigger a comment wake. Re-read current readiness on wake. Use `unwatch_pull_request` at handoff/completion. CLI-created PRs still need native linking. |
| Browser proof | Start with `preview_status`; if no automation-capable preview is attached, try `preview_open` before claiming no browser. Use `preview_snapshot` and focused `preview_*` interactions, preferring snapshot locators. Read a human-owned tab but do not drive it; never operate another agent session's tab. Parallel subagents sharing a provider session each open with `reuseExistingTab=false` and pass their returned `tabId` on every call. Follow the runtime's documented fallback threshold and report the raw error. A requested named browser or project-specific browser procedure retains its route. |
| Mobile proof | `device_list`, then `device_open`; drive through the exact returned `agent-device` launcher and keep its host/context flags. Prefer snapshot refs; use `device_screenshot` for visual evidence. Read the real device result before claiming availability. |
| Explain visually | For a useful chart, flow or preview, check self-contained HTML with `html_preview`, then show it through `html_render` before the final reply. This is conversation content, not a deployed site. Native plans/checkpoints show phase; do not invent a taskbar progress setter. |
| Secrets and recurring work | When user secret input is actually needed and the tool is available, use `request_secret` and its private reference, never chat or a copied value. Schedule only requested persistent work through `schedule_task` with its structured schedule; a pending PR uses its watcher instead. Scheduling alone grants no development, data or deployment authority. |

These tools implement the existing task and project rules. They do not replace agent-work ownership, prove acceptance, grant external-message authority or bypass native approval. Standalone module use keeps the same boundaries. Using the host by itself does not justify a new top-level chat, recurring job or permission flow.

## Delivery and authority

File/update a concise problem-first PR, record URL on the same task and link it through native T3 PR linking. Only its lead owns the native PR watch. Check current head/base/checks before merge/readiness; verify release identity before/after live proof. Auto-deploying merge is a deployment. Model verdicts are not human GitHub approvals.

Full Send reuses the user's concrete assignment for the established unambiguous test target and repair heads; stricter project gates remain. The actual qualified lead records stage_authorize_chat where required for exact task/repo/PR/head/context, quoting the real instruction and native source reference. Then stage_begin and delivery use that head and actual release proof. Never fabricate references, copy another actor's attestation or infer prod permission. The current stage adapter constrains target/base; other test targets use their actual project mechanism, never forged stage bindings.

Full Stop hands off the ready unmerged PR with Done / Verified / Unresolved / Next. Do not fake delivery to complete a deployment-bound ticket; it retains its real waiting lifecycle until delivery or a legitimate changed endpoint. Genuine local-only tasks can use none. Complete needs acceptance, closed children/dependencies, proportional lead Retro, final comment and real evidence. Field validation does not prove content true.

Block retains ownership; handoff releases it with next action. Recover needs expired ownership and confirmation the previous owner stopped. Parent cancellation verifies native child work stopped before previous_stopped; never erase unfinished work with cancellation. Existing pickup batches use supported pickup_continue/bind_self under the actual lead. Pause/disable is supported; resume/enable/increased limits retain native human gates. Never fake human/service, TTY, CSRF or DB state. No new pickup policy or recurring job follows from this workflow alone.

## Native Windows boundary

The current Windows host has no native agent-work registry adapter. Installed skills and native Computer Use do not establish registry availability. Use a verified supported project-host route when it supplies the necessary task ownership/proof (WORKABLE); otherwise report the exact registry prerequisite as BLOCKER and continue independent authorized work. Never invent a Windows registration or task state. Windows skill mirrors must be regenerated and checked after shared workflow changes.
