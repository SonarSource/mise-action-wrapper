# mise-action-wrapper

Wrapper for [`step-security/mise-action`](https://github.com/step-security/mise-action) within SonarSource CI.

This wrapper centralises:

- Pinned `step-security/mise-action` and `mise` versions
- S3-backed caching via [`SonarSource/gh-action_cache`](https://github.com/SonarSource/gh-action_cache)
- Cache integrity validation (corrupt restore / version mismatch recovery)
- Repox authentication for mise backends (`pipx`, `uv`, `npm`, Maven)
- Poetry short name forced onto `pipx:poetry` so installs go through Repox, not
  the vfox installer that contacts PyPI

## Usage

```yaml
- name: Install tools using mise
  uses: SonarSource/mise-action-wrapper@v2
```

Inputs use the same names as [`step-security/mise-action`](https://github.com/step-security/mise-action), so a
`with:` block written for it works here, apart from the inputs listed under [Not supported](#not-supported).

The point of this wrapper is its S3 cache, keyed on the runner OS, the mise version, the mise configuration files,
`mise_toml`, `tool_versions`, `install`, `install_args`, `plugins` and the `bootstrap*` inputs. Jobs that install
different tool sets from the same configuration get different keys without setting `cache_key_prefix`.
Restore keys never cross mise versions: tools installed by another mise version can be listed as installed
while their binaries are missing from `PATH`. `step-security/mise-action` is always called with `cache: false`.

## Inputs

### Same as step-security/mise-action

Passed through unchanged, with the upstream default: `add_shims_to_path`, `bootstrap`, `bootstrap_args`,
`bootstrap_skip`, `env`, `experimental`, `export_path`, `fetch_from_github`, `github_token`, `install`,
`install_args`, `log_level`, `mise_toml`, `plugins`, `reshim`, `sha256`, `tool_versions`,
`working_directory`.

Passed through with a different default:

| Input | Default | Why |
|-------|---------|-----|
| `persist_github_token` | `true` | Keeps MISE_GITHUB_TOKEN available to later steps, as in mise-action v2 to v5.1.0. |
| `version` | `2026.11.8` | Pinned so every job runs a known mise release; Renovate bumps it. |

### Implemented by the wrapper

| Input | Default | Description |
|-------|---------|-------------|
| `cache` | `true` | The S3 cache is always on. `false` fails the job; use `step-security/mise-action` directly for an uncached install |
| `cache_key_prefix` | `mise` | Prefix of the S3 cache key |
| `artifactory_reader_role` | _(auto)_ | Vault Artifactory role suffix (`public-reader` / `private-reader`) |
| `repox_url` | `https://repox.jfrog.io` | Repox base URL |
| `vault_url` | `https://vault.sonar.build` | Vault URL for credential fetch |

### Not supported

Setting any of these fails the job with the reason:

| Input | Reason |
|-------|--------|
| `auto_update` | The wrapper pins the mise version. |
| `cache_key` | The wrapper builds its own S3 cache key; use cache_key_prefix. |
| `cache_save` | The wrapper always saves its S3 cache. |
| `cache_save_post` | The wrapper always saves its S3 cache in the post step. |
| `install_dir` | Deprecated upstream. |
| `minimum_release_age` | The wrapper pins the mise version, so upstream ignores it. |
| `mise_dir` | The wrapper's cache and integrity checks rely on the default mise directory. |
| `wings_enabled` | Sends downloads through a third-party asset cache. |

## Outputs

| Output | Description |
|--------|-------------|
| `cache-hit` | `true` when the S3 cache was restored from an exact key match |
| `versions` | JSON object of the installed tool versions, as reported by `step-security/mise-action` |

## Upgrading from v1

2.0.0 renames the inputs that differed from `step-security/mise-action`. The old names fail the job with the new name,
instead of being ignored with a warning.

| v1 | v2 |
|----|----|
| `artifactory-reader-role` | `artifactory_reader_role` |
| `cache-key-prefix` | `cache_key_prefix` |
| `mise-toml` | `mise_toml` |
| `mise-version` | `version` |
| `repox-url` | `repox_url` |
| `vault-url` | `vault_url` |

[`SonarSource/renovate-config`](https://github.com/SonarSource/renovate-config) bumps the pinned `version:` of
v2 callers as it bumped `mise-version:` for v1 callers.

The cache key now also covers `install`, `install_args`, `plugins` and the `bootstrap*` inputs, so expect one cache miss
per job after upgrading.

## Staying aligned with step-security/mise-action

[`upstream-inputs.yaml`](upstream-inputs.yaml) classifies every input of the pinned `step-security/mise-action`.
CI runs [`scripts/check_upstream_contract.py`](scripts/check_upstream_contract.py), which fails when an upstream input
is added, removed or changes its default, when a forwarded input is not passed through, or when an input is declared
but unused. When a Renovate update of the pinned action fails this check, classify the new inputs in
`upstream-inputs.yaml` and update `action.yaml`.

## Repox behaviour

The wrapper always:

1. Fetches Artifactory credentials via [`SonarSource/vault-action-wrapper@v3`](https://github.com/SonarSource/vault-action-wrapper)
2. Exports Python index env vars (`PIP_INDEX_URL`, `UV_DEFAULT_INDEX`, `MISE_PIPX_REGISTRY_URL`)
3. Forces the `poetry` short name onto the pipx backend (`MISE_BACKENDS_POETRY=pipx:poetry`) so `poetry = "…"` in `mise.toml` does not use
   mise’s default vfox plugin (which curls `install.python-poetry.org` and looks up `pypi.org/pypi/poetry/json`)
4. Writes `~/.npmrc` for the npm backend
5. Writes `~/.netrc` and `MISE_URL_REPLACEMENTS` so mise HTTP downloads from Maven Central go through Repox (`/maven2/` stripped to match
   Artifactory layout)

You do **not** need to run `config-pip` before mise for tools installed through mise (`pipx:`, `uv`, `poetry`, etc.). Keep using
[`config-pip`](https://github.com/SonarSource/ci-github-actions/tree/master/config-pip) for `setup-python`, standalone `pip`, or `pipx` that
do not go through mise.

### Poetry backend

Mise’s registry prefers [`vfox:mise-plugins/vfox-poetry`](https://github.com/mise-plugins/vfox-poetry)
over `pipx:poetry`. That plugin fetches `install.python-poetry.org` and resolves versions via
`pypi.org/pypi/poetry/json`, so the install still reaches the public internet even with
`PIP_INDEX_URL` set. This wrapper
overrides it with [`MISE_BACKENDS_POETRY`](https://mise.jdx.dev/registry.html#environment-variable-overrides)
so both of these install Poetry from Repox:

```toml
[tools]
python = "3.13"
poetry = "2.2.1"        # rewritten to pipx:poetry
"pipx:poetry" = "2.2.1" # explicit; same backend
```

pipx needs a Python interpreter on `PATH`. Declare `python` in the same `mise.toml` (or ensure the runner already has one). vfox-only
options such as `pyproject` auto-venv / `MISE_POETRY_VENV_AUTO` do not apply on this path.

## Requirements

- Job must have `id-token: write` (Vault JWT auth)
- Repository must have a matching Artifactory reader token in Vault

## Reference

Based on the local
[`sonar-security` mise wrapper](https://github.com/SonarSource/sonar-security/blob/master/.github/actions/mise-wrapper/action.yml).
