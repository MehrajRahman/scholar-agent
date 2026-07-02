# Contributing to scholar-agent

Thanks for considering a contribution — whether it's a bug fix, a new
provider integration, a prompt improvement, or just a typo fix, it's welcome.

## Ground rules

- Be respectful in issues and PRs. Assume good faith.
- Open an issue before starting large or architectural changes, so we can
  agree on the approach before you invest the time.
- Small, focused PRs are much easier to review than large ones — prefer
  several small PRs over one giant one.

## Getting set up

```bash
git clone https://github.com/<you>/scholar-agent.git
cd scholar-agent
python3 -m venv .venv && source .venv/bin/activate
make dev                          # editable install + dev extras (pytest, ruff, mypy)

cp .env.example .env              # fill in what you need; never commit real keys
cp providers.json.example providers.json   # optional multi-provider pool
```

You don't need every backend running to contribute — most of the codebase is
covered by offline unit tests. If you're working on something that needs the
full stack (Neo4j/Qdrant/an LLM), see [README.md § Quick start](README.md#quick-start)
and confirm everything's reachable with:

```bash
make check
```

## Before you open a PR

```bash
make lint     # ruff + mypy — both must be clean (enforced in CI)
make test     # 48 offline unit tests — must pass (enforced in CI)
```

CI gates on `ruff`, `mypy`, and `pytest` — keep all three green. The codebase is
fully type-checked (`mypy src` is clean), so please keep it that way in any files
you touch.

If you added new behavior, **add a test** — see `tests/` for the existing
style (pure/offline unit tests grouped by module: `test_ranking.py`,
`test_matchmaker.py`, `test_api.py`, etc.). Live-infra changes should also
pass `make check` locally before you submit.

## Commit / PR conventions

- Write commit messages that explain **why**, not just what changed.
- Keep the diff scoped to the stated purpose of the PR — unrelated
  refactors/reformatting make review harder.
- Reference the issue you're addressing, if any (`Fixes #12`).
- CI (when configured) must pass before merge.

## Where to start

Good first contributions:
- A new LLM provider entry in `providers.json.example` + a short note in the
  README if it needs anything special.
- Widening `tools/ranking.py`'s reputation list with more scholarship
  registries you know are reliable.
- Extra `ArtifactType`s in `agents/kit.py` (e.g. a new document format).
- Prompt tuning in `prompts/templates/` — especially adding few-shot examples
  for a field/domain the matchmaker currently handles poorly.
- Test coverage for any module in `src/scholar/` that doesn't have one yet.

If you're not sure where to start, open an issue describing what you'd like
to work on and we can figure it out together.

## Reporting bugs vs. security issues

- **Bugs**: open a GitHub issue with steps to reproduce, what you expected,
  and what happened instead (include relevant log output if you can).
- **Security vulnerabilities**: do **not** open a public issue — see
  [SECURITY.md](SECURITY.md) for how to report privately.

## Code style

- Python 3.11+, type-hinted, formatted/linted with `ruff` (line length 100).
- Each agent is a pure `async (state) -> partial_state` function — keep new
  agents/nodes in that shape so they compose cleanly in `graph_app.py`.
- Prefer adding a template under `prompts/templates/<agent>/` over editing
  the inline fallback prompts in `agents/prompts.py`, unless the change should
  apply to every model family.

## License

By contributing, you agree that your contributions will be licensed under the
project's [MIT License](LICENSE).
