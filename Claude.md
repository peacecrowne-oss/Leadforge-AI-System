# Claude Code Rules (Repo Root)

## Non-negotiables
- Do not change code unless explicitly asked in the current step.
- One scoped change per step (one file if possible).
- Before editing: explain what will change and why.
- After editing: show the diff or describe exact file changes.
- Do not refactor or “clean up” unrelated code.
- Do not add dependencies unless explicitly approved.
- Prefer simplest working solution over cleverness.
- If requirements are missing, ask; do not guess.
- Never store “requirements” in the repo; requirements live in the Custom GPT instructions.

## Safety & Verification
- If a command is suggested, explain what it does and what output to expect.
- If something fails, stop and ask for the error output.