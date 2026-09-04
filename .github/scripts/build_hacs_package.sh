#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_path="${1:-${repository_root}/halthy.zip}"

if [[ "${output_path}" != /* ]]; then
  output_path="${repository_root}/${output_path}"
fi

staging_directory="$(mktemp -d)"
trap 'rm -rf "${staging_directory}"' EXIT

# HACS extracts release ZIP contents directly into custom_components/halthy.
cp -R "${repository_root}/custom_components/halthy/." "${staging_directory}/"
rm -rf "${staging_directory}/tests"
find "${staging_directory}" -name '.DS_Store' -delete
find "${staging_directory}" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${staging_directory}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

rm -f "${output_path}"
(
  cd "${staging_directory}"
  zip -qr "${output_path}" .
)

archive_contents="$(unzip -Z1 "${output_path}")"

for required_file in __init__.py manifest.json strings.json; do
  if ! grep -qx "${required_file}" <<<"${archive_contents}"; then
    echo "Required file is missing from the archive root: ${required_file}" >&2
    exit 1
  fi
done

if grep -Eq '^custom_components(/|$)' <<<"${archive_contents}"; then
  echo "Invalid HACS archive: custom_components must not be inside the release ZIP." >&2
  exit 1
fi

if grep -Eq '(^|/)(tests|__pycache__)(/|$)|(^|/)\.DS_Store$|\.py[co]$' <<<"${archive_contents}"; then
  echo "Invalid HACS archive: development or generated files are included." >&2
  exit 1
fi

echo "Built valid HACS package: ${output_path}"
