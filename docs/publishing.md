# Publishing (maintainers)

## 1. Make the GitHub repository public

```bash
gh repo edit umithavare/unwedge --visibility public --accept-visibility-change-consequences
```

Until then, `/plugin marketplace add umithavare/unwedge` only works for accounts that can read
the private repository.

## 2. Publish to PyPI (trusted publishing, no token)

One-time setup on pypi.org (logged in as the package owner):

1. Account settings → Publishing → "Add a new pending publisher".
2. PyPI project name `unwedge`, owner `umithavare`, repository `unwedge`,
   workflow `release.yml`, environment `pypi`.
3. In the GitHub repository: Settings → Environments → New environment `pypi`
   (optionally require your approval for each release).

Release:

```bash
# bump the version in pyproject.toml, src/unwedge/__init__.py and both plugin manifests,
# add a CHANGELOG entry, then:
git tag v0.1.0
git push origin v0.1.0
```

The `release` workflow builds the sdist and wheel and uploads them. Afterwards:

```bash
uv tool install unwedge        # or pipx / pip
```

Before the first PyPI release, users can install from GitHub:
`uv tool install git+https://github.com/umithavare/unwedge`.

## 3. Claude Code plugin

Nothing to publish: the repository is its own marketplace (`.claude-plugin/marketplace.json`).
Users run `/plugin marketplace add umithavare/unwedge` and `/plugin install unwedge@unwedge`,
and get updates with `/plugin marketplace update`. Validate changes with:

```bash
claude plugin validate --strict plugins/claude-code
claude plugin validate --strict .
```

Keep the plugin `version` in step with the Python package, since the plugin calls the `unwedge` CLI.

## 4. Codex

The repository also carries a Codex marketplace (`.agents/plugins/marketplace.json`) pointing
at `plugins/codex`. Users add it with `codex plugin marketplace add umithavare/unwedge`. The
documented, tested path for Codex is still the `hooks.json` snippet in [codex.md](codex.md).

## 5. Checklist for a release

- `ruff check src tests benchmarks` and `pytest -q` pass (CI does this on Linux, macOS and Windows).
- `unwedge doctor` works with each provider you have access to.
- Benchmark numbers in the README still match `benchmarks/results/` if the policy changed
  (`python benchmarks/analyze.py --variant plain`).
