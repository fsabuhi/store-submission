# Working on store-submission

Store Submission is one Agent Skill, `skills/store-submission/`, packaged for several agents.

- `SKILL.md` is what an agent loads: the workflow from fetching the rules to cleanup. `references/` holds the checklists, the official sources and the baseline; `scripts/` holds the fetcher, the scanner and their tests.
- **Live rules win.** `references/sources.json` lists the official pages. `references/baseline.json` records the section hashes the reference files were last checked against. When the fetcher reports changed sections, update the matching reference file, then run `fetch_guidelines.py --out <dir> --update-baseline` and commit both together.
- **Vendored files.** `references/apple/` is copied unchanged from safaiyeh/app-store-review-skill. `references/google-play/*.json` is copied unchanged from android/skills; the `.md` files there are adapted from it and say so at the top. `scripts/scan.py` ports Greenlight's rules. When any of them is refreshed from upstream, update the commit in `THIRD-PARTY-NOTICES.md`.
- **Scripts** are standard-library Python 3.11+, so `uv run` needs no install. Every scanner rule and every fix has a test in `scripts/test_store_submission.py`, and a fix's test fails without it.
- Run the tests on Python 3.11 and on the newest Python: `uv run --python 3.11 python -m unittest discover -s skills/store-submission/scripts -p 'test_*.py'`.
- A release bumps the version in every manifest together: `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.github/plugin/plugin.json` and `gemini-extension.json`.
