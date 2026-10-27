# example-app project pack

Read only the rows that match the actual change.

| Change | Procedure | Notes |
|---|---|---|
| Any code change | Project `AGENTS.md`, then `docs/DEVELOPMENT-WORKFLOW.md` in the repo | Branch rules, required CI, review requirement. |
| New page or surface | `intake.md` (private, not in this example) | Has a retained human gate: new surfaces need owner approval of the route name. |
| Auth or permission change | `auth-setup.md` (private, not in this example) | Always R2 or higher. Full Stop candidate if shared session behavior changes. |
| Deploy to test | `DEPLOY.md` in the repo | Test target: `stage`. Production needs explicit task-specific authority. |
| Verify behavior | [verify-example-app/SKILL.md](verify-example-app/SKILL.md) | Run affected recipes only. |

Before deploying to `stage`, follow the project's actual shared-target coordination and approval procedure. A ticket number itself grants no deployment permission.
