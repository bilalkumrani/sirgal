# Contributing to Sirgal

Thanks for wanting to help. Sirgal reads company files, so contributions are held to a high bar. The rules below aren't bureaucracy; they're how we keep the promises people rely on when they run it.

Before you start, please read the [Code of Conduct](CODE_OF_CONDUCT.md). To report a security problem, follow [SECURITY.md](SECURITY.md) instead of opening an issue.

## The rules every change must follow

These are not negotiable. A pull request that breaks one won't be merged, however useful it is.

1. **Read-only.** Sirgal never changes, deletes or re-shares anything unless a future, explicit opt-in feature asks for separate permission.
2. **File contents are never kept.** Files are read in memory and dropped right after checking. Never write contents to disk, a log, a cache, an error message or a report.
3. **Counts, never values.** Detectors report what kind of data was found and how many, like `{"ssn": 25}`. Never the values themselves.
4. **Nothing leaves the machine.** No network calls except to the cloud service being scanned, plus the one-time model download when a user chooses the model. No telemetry, no outside AI services.
5. **Unknown is never OK.** If a shared file can't be read, it's UNKNOWN, never OK.
6. **No real data, anywhere.** Use only the sample test company from `scripts/make_test_data.py`. Never put real file names, contents, emails or tokens in code, tests, issues, pull requests or screenshots.

## Before you start

- **Find or open an issue first**, and say you'd like to work on it. For anything bigger than a small fix, describe your approach and wait for a reply before writing code. It saves everyone from a rejected pull request.
- **Keep pull requests small**: one change, one purpose.

## Set up

Requires Python 3.10 or newer.

```
git clone https://github.com/bilalkumrani/sirgal.git
cd sirgal
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check
```

Both commands must pass before you start, so you know any failure later is yours.

To try real scans, create the sample company with `python3 scripts/make_test_data.py`, upload it to a **test** Google account, and follow the Quick start in the README. Never point a development build at real company data.

## Workflow

1. **Fork** the repository (or branch, if you're a maintainer).
2. **Create a branch** named after the change:
   - `feature/short-description` for new features
   - `fix/short-description` for bug fixes
   - `docs/short-description` for documentation
3. **Make the change, with tests.**
4. **Check locally**: `pytest` and `ruff check` must both pass.
5. **Commit** with a short message in the imperative mood, like `Add OCR for scanned PDFs` or `Fix timeout during file download`.
6. **Open a pull request** against `main` and fill in the template. Link the issue with `Fixes #123`.
7. **Checks run automatically**: tests on Python 3.10 to 3.13, and the style check. Every check must be green.
8. **A maintainer reviews and merges.** Pull requests are squash-merged, so each one becomes a single commit on `main`.

Nobody pushes directly to `main`, maintainers included.

## Tests

- **Every change needs tests.** Bug fixes need a test that fails without the fix.
- **Tests never touch the network or download anything.** Google is replaced with a fake, and the model with a stand-in. See `tests/test_gdrive.py` and `tests/test_ner.py` for how.
- **Detection changes must keep the answer key passing.** `tests/test_test_data.py` checks the detectors against `manifest.json` for several seeds. If you add a new kind of detection, add matching files to the sample company, including at least one **harmless** file that must stay OK. Catching more isn't progress if it also raises false positives.
- **Model changes need numbers.** If you touch `src/sirgal/ner.py` or the model rules, run `python3 scripts/compare_detectors.py` and paste the summary into the pull request.

## Code style

- `ruff check` must pass. The settings live in `pyproject.toml`.
- Prefer clear names over comments. Use comments to explain *why*, not *what*.
- Every module and public function gets a short docstring.
- Anything a user reads, like terminal output, reports and docs, uses plain English. No jargon where a simple word works.

## Dependencies

- Avoid new dependencies. If one is truly needed, explain why in the pull request.
- Heavy dependencies, like machine learning libraries, go in an optional extra (see `ner` in `pyproject.toml`), never in the core install.

## Releases

Releases are done by maintainers: version bump, PyPI upload, tag and GitHub release.

## License

By contributing, you agree that your contribution is licensed under the [Apache License 2.0](LICENSE), the same license as the project.
