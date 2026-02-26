# Releasing

This project uses GitHub Actions to publish releases to GitHub and PyPI when `project.version` changes in `pyproject.toml` on a commit pushed to `main`.

## One-time setup (PyPI Trusted Publishing)

1. Create the project on PyPI if it does not exist yet.
2. In PyPI, open your project settings and add a Trusted Publisher with:
   - Owner: your GitHub user/org that owns this repo
   - Repository name: `python-dropbox-api`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. In GitHub, ensure Actions are enabled for the repository.

The workflow permissions are:
- `contents: write` (create tag + GitHub Release)
- `id-token: write` (PyPI OIDC token exchange)

## Release process

1. Ensure you are on `main` and up to date:

```bash
git checkout main
git pull --ff-only
```

2. Update `project.version` in `pyproject.toml`.

3. Commit and push to `main`:

```bash
git add pyproject.toml
git commit -m "Bump version to 0.1.3"
git push origin main
```

4. Verify the GitHub Actions `Release` workflow succeeds.

On success, CI will:
- create and push tag `0.1.3` (matching `project.version`)
- create a GitHub Release with `sdist` and `wheel` artifacts
- publish the same artifacts to PyPI

## Guardrails in CI

- If `project.version` did not change, the workflow exits without releasing.
- If the version tag already exists, the workflow fails instead of overwriting.
