#!/usr/bin/env bash
# Copyright 2026 The Volcano Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GO_HDR="${ROOT}/hack/boilerplate.go.txt"
PY_HDR="${ROOT}/hack/boilerplate.py.txt"

prepend_if_missing() {
  local file="$1"
  local hdr="$2"
  local first
  first="$(head -1 "$file" 2>/dev/null || true)"
  if [[ "$first" == *Copyright* ]]; then
    return 0
  fi
  local tmp
  tmp="$(mktemp)"
  cat "$hdr" >"$tmp"
  echo >>"$tmp"
  cat "$file" >>"$tmp"
  mv "$tmp" "$file"
}

while IFS= read -r -d '' f; do
  prepend_if_missing "$f" "$GO_HDR"
done < <(find "${ROOT}" -name '*.go' -not -path '*/vendor/*' -print0 2>/dev/null)

while IFS= read -r -d '' f; do
  prepend_if_missing "$f" "$PY_HDR"
done < <(find "${ROOT}" -name '*.py' -not -path '*/.venv/*' -not -path '*/vendor/*' -print0 2>/dev/null)

echo "Copyright headers applied where missing."
