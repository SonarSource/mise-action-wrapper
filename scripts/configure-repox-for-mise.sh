#!/usr/bin/env bash

set -euo pipefail

: "${ARTIFACTORY_URL:?}" "${ARTIFACTORY_USERNAME:?}" "${ARTIFACTORY_ACCESS_TOKEN:?}" "${GITHUB_ENV:?}"

configure_python_backends() {
  local authenticated_index registry_url

  authenticated_index="${ARTIFACTORY_URL%/}/api/pypi/sonarsource-pypi/simple"
  authenticated_index="https://${ARTIFACTORY_USERNAME}:${ARTIFACTORY_ACCESS_TOKEN}@${authenticated_index#https://}"
  registry_url="${authenticated_index%/}/{}/"

  echo "::add-mask::${authenticated_index}"
  echo "::add-mask::${registry_url}"
  {
    echo "PIP_INDEX_URL=${authenticated_index}"
    echo "UV_DEFAULT_INDEX=${authenticated_index}"
    echo "MISE_PIPX_REGISTRY_URL=${registry_url}"
  } >> "$GITHUB_ENV"
}

configure_npm_backend() {
  local npm_registry npm_host

  npm_registry="${ARTIFACTORY_URL%/}/api/npm/npm"
  npm_host="${ARTIFACTORY_URL#https:}"

  cat >> "${HOME}/.npmrc" <<EOF
registry=${npm_registry}
${npm_host}/api/npm/:_authToken=${ARTIFACTORY_ACCESS_TOKEN}
EOF
}

configure_netrc() {
  local repox_host

  repox_host="${ARTIFACTORY_URL#https://}"
  repox_host="${repox_host#http://}"
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
