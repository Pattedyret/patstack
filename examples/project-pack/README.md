# Example project pack

A project pack holds the project-specific procedures Patstack reads after it binds the workspace: intake rules, auth conventions, deploy and sync steps, and the verification recipes `create-test-recipes` maintains.

This directory is a **sanitized, fictional example** for an app called `example-app`. Real project packs stay private and local, next to the shared setup source (`project-skills/<project>/`) or inside the project repository where its own instructions say. They are never published with this package.

| File | Role |
|---|---|
| [INDEX.md](INDEX.md) | Router: which procedure applies to which kind of change. Patstack reads this first and loads nothing else by default. |
| [verify-example-app/SKILL.md](verify-example-app/SKILL.md) | Verification skill in the shape `create-test-recipes` generates: Launch, Doctor, Run, Evidence, Cleanup. |
| [verify-example-app/recipes/sign-in.md](verify-example-app/recipes/sign-in.md) | One recipe per coherent user journey, with negative cases and last verified revision. |

Keep credentials, device addresses and account names out of every file here. Recipes name a test persona by alias (`persona: reviewer-basic`) and the vault item is resolved at run time through the access policy.
