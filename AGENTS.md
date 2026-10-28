# SmartSimulator — Development Rules

## Working approach
- Work in small, independently testable features.
- Read the existing code, project plan, and Git status before changing files.
- Preserve existing user work. Never discard unrelated changes.
- Use the project requirements and assignment as the source of truth.
- Prefer simple, maintainable Python code and deterministic simulations.
- Never make real telephone calls or use paid telecom services.

## Required workflow for each feature
1. Explain the planned changes briefly.
2. Implement the feature.
3. Run relevant tests, lint checks, and static checks that are available.
4. Inspect the final diff for correctness, unintended changes, secrets, and data exposure.
5. Report the files changed, tests executed, actual results, and any unresolved issues.
6. STOP and wait for my explicit approval before committing or pushing.

## Git approval policy
- Never run `git commit`, `git push`, `git merge`, or a pull-request merge without my explicit approval in the current conversation.
- Never force-push or rewrite history.
- Never push directly to `main`.
- Never stage all files blindly. Review `git status` and stage only intended files.
- Do not commit `.env` files, credentials, private data, raw company datasets, local databases, virtual environments, or generated artifacts.
- Do not claim tests passed unless they were actually executed successfully.
- If a test cannot run, explain why and report it as unverified.
- Keep work on the current approved feature branch unless I authorize a branch change.

## Quality requirements
- Add tests for new behavior and bug fixes.
- Test state transitions, duplicate events, out-of-order events, concurrent reservations, provider outages, and recovery where relevant.
- Keep CI reproducible and independent of real telecom APIs and external paid services.
- Update README and technical documentation when behavior or setup changes.
- Maintain a project backlog and record meaningful architectural decisions.

## Completion report
Before requesting approval, provide:
- Summary of implementation
- Files added or changed
- Commands run and their real results
- Remaining risks or limitations
- Git diff summary
- Recommended commit message

Wait for my approval before committing or pushing anything.