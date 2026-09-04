# mise-action-wrapper

Wrapper for [`jdx/mise-action`](https://github.com/jdx/mise-action) within SonarSource CI.

This wrapper centralises:

- Pinned `jdx/mise-action` and `mise` versions
- S3-backed caching via [`SonarSource/gh-action_cache`](https://github.com/SonarSource/gh-action_cache)
- Cache integrity validation (corrupt restore / version mismatch recovery)
- Repox authentication for mise backends (`pipx`, `uv`, `npm`, Maven)

## Usage

Replace direct `jdx/mise-action` usage for typical install-from-config jobs:

```yaml
- name: Install tools using mise
  uses: SonarSource/mise-action-wrapper@v1
```

With a custom cache prefix when multiple jobs install different tool sets:

```yaml
- name: Install tools using mise
  uses: SonarSource/mise-action-wrapper@v1
  with:
    cache-key-prefix: mise-qa
```

Caching is handled by this wrapper (`cache: false` is always passed through to
`jdx/mise-action`). Forwarded `jdx/mise-action` inputs: `install`,
`install_args`, `working_directory`, `tool_versions`, `reshim`, `experimental`,
`github_token`, `log_level`, and `mise_toml` (as `mise-toml`).

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `cache-key-prefix` | `mise` | Prefix for the S3/GitHub cache key |
| `mise-toml` | _(empty)_ | Optional `mise.toml` content written before install |
| `mise-version` | `2026.8.15` | Pinned mise version installed by the wrapper |
| `repox-url` | `https://repox.jfrog.io` | Repox base URL |
| `artifactory-reader-role` | _(auto)_ | Vault Artifactory role suffix (`public-reader` / `private-reader`) |
| `vault-url` | `https://vault.sonar.build` | Vault URL for credential fetch |
| `install` | `true` | If `false`, skip `mise install` |
| `install_args` | _(empty)_ | Arguments passed to `mise install` |
| `working_directory` | _(empty)_ | Directory that mise runs in |
| `tool_versions` | _(empty)_ | Optional `.tool-versions` content written before install |
| `reshim` | `false` | If `true`, run `mise reshim --all` after setup |
| `experimental` | `false` | Enable experimental mise features |
| `github_token` | `${{ github.token }}` | Token for GitHub-hosted tool downloads |
| `log_level` | `info` | mise log level |

## Repox behaviour

The wrapper always:

1. Fetches Artifactory credentials via
   [`SonarSource/vault-action-wrapper@v3`](https://github.com/SonarSource/vault-action-wrapper)
2. Exports Python index env vars
   (`PIP_INDEX_URL`, `UV_DEFAULT_INDEX`, `MISE_PIPX_REGISTRY_URL`)
3. Writes `~/.npmrc` for the npm backend
4. Writes `~/.netrc` and `MISE_URL_REPLACEMENTS` so mise HTTP downloads from
   Maven Central go through Repox (`/maven2/` stripped to match Artifactory layout)

You do **not** need to run `config-pip` before mise for tools installed through
mise (`pipx:`, `uv`, etc.). Keep using
[`config-pip`](https://github.com/SonarSource/ci-github-actions/tree/master/config-pip)
for `setup-python`, standalone `pip`, or `pipx` that do not go through mise.

## Requirements

- Job must have `id-token: write` (Vault JWT auth)
- Repository must have a matching Artifactory reader token in Vault

## Reference

Based on the local
[`sonar-security` mise wrapper](https://github.com/SonarSource/sonar-security/blob/master/.github/actions/mise-wrapper/action.yml).
