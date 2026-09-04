#!/usr/bin/env bash

set -euo pipefail

: "${ARTIFACTORY_URL:?}" "${ARTIFACTORY_USERNAME:?}" "${ARTIFACTORY_ACCESS_TOKEN:?}" "${GITHUB_ENV:?}"

configure_python_backends() {
  local scheme host_and_path authenticated_index registry_url

  scheme="${ARTIFACTORY_URL%%://*}"
  host_and_path="${ARTIFACTORY_URL#*://}"
  authenticated_index="${scheme}://${ARTIFACTORY_USERNAME}:${ARTIFACTORY_ACCESS_TOKEN}@${host_and_path%/}/api/pypi/sonarsource-pypi/simple"
  # mise derives PIP_INDEX_URL from this URL; Artifactory's JSON API does not convert to a valid simple index, so pipx installs fail.
  registry_url="${authenticated_index}/{}/"

  echo "::add-mask::${authenticated_index}"
  echo "::add-mask::${registry_url}"
  {
    echo "PIP_INDEX_URL=${authenticated_index}"
    echo "UV_DEFAULT_INDEX=${authenticated_index}"
    echo "MISE_PIPX_REGISTRY_URL=${registry_url}"
  } >> "$GITHUB_ENV"
}

configure_npm_backend() {
  local npm_registry npm_host host_and_path

  host_and_path="${ARTIFACTORY_URL#*://}"
  npm_registry="${ARTIFACTORY_URL%/}/api/npm/npm"
  npm_host="//${host_and_path}"

  cat >> "${HOME}/.npmrc" <<EOF
registry=${npm_registry}
${npm_host}/api/npm/:_authToken=${ARTIFACTORY_ACCESS_TOKEN}
EOF
  chmod 600 "${HOME}/.npmrc"
}

configure_netrc() {
  local repox_host

  repox_host="${ARTIFACTORY_URL#*://}"
  repox_host="${repox_host%%/*}"

  cat >> "${HOME}/.netrc" <<EOF
machine ${repox_host}
  login ${ARTIFACTORY_USERNAME}
  password ${ARTIFACTORY_ACCESS_TOKEN}
EOF
  chmod 600 "${HOME}/.netrc"
}

configure_mise_url_replacements() {
  local replacements

  # Host-only replacement would keep /maven2 and 404 on Artifactory.
  # See https://mise.jdx.dev/url-replacements.html
  replacements="$(jq -cn \
    --arg dest "${ARTIFACTORY_URL%/}/central/" \
    '{
      "regex:^https://(repo\\.maven\\.apache\\.org|repo1\\.maven\\.org)/maven2/": $dest
    }')"

  echo "MISE_URL_REPLACEMENTS=${replacements}" >> "$GITHUB_ENV"
}

configure_repox_for_mise() {
  echo "::add-mask::${ARTIFACTORY_ACCESS_TOKEN}"
  configure_python_backends
  configure_npm_backend
  configure_netrc
  configure_mise_url_replacements
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  configure_repox_for_mise
fi
