#!/usr/bin/env bash
# Publish a GitHub Release for every connector version that doesn't have one
# yet. Idempotent: versions that already have a release are skipped, so dropping
# several older .tgz files into connectors/ backfills all of them in one run.
#
# A version is detected from either:
#   connectors/<app>-v<X.Y.Z>.tgz         a committed package (used as-is), or
#   connectors/source/<app>/<app>.json     an app_version with no committed
#                                          package: built from source/ here
# A committed package wins over building from source.
#
# Each release is tagged <app>-v<X.Y.Z> on the commit that introduced that
# version, with the .tgz and a .sha256 (to verify it after an air-gap transfer).
#
# Before publishing, a committed package is checked for desync: the version
# inside it must match the file name, and (for the version currently in
# connectors/source/) the extracted contents must match source/.
#
# Needs gh (GH_TOKEN for auth, GH_REPO for the repo), jq, and full git history.
# DRY_RUN=1 prints what would be published without creating anything.
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
VERSION_RE='^[0-9]+\.[0-9]+\.[0-9]+$'

fail() { echo "::error::$*"; exit 1; }

cd "$(git rev-parse --show-toplevel)"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/built"

shopt -s nullglob
released=$(gh release list --limit 1000 --json tagName --jq '.[].tagName')

# One "<file name><TAB><path>" line per candidate package.
candidates=()
declare -A built_at  # file -> commit, for packages built from source/ below

for pkg in connectors/*-v*.tgz; do
  candidates+=("$(basename "$pkg")"$'\t'"$pkg")
done

for meta in connectors/source/*/*.json; do
  app=$(basename "$(dirname "$meta")")
  [ "$(basename "$meta")" = "$app.json" ] || continue
  version=$(jq -r .app_version "$meta")
  [[ $version =~ $VERSION_RE ]] || fail "$meta: app_version '$version' is not X.Y.Z"
  file="$app-v$version.tgz"
  [ ! -f "connectors/$file" ] || continue
  ! grep -qxF "${file%.tgz}" <<<"$released" || continue

  wheels=$(jq '[.pip_dependencies, .pip39_dependencies, .pip313_dependencies | (.wheel // []) | length] | add' "$meta")
  [ "$wheels" = 0 ] || fail "$meta lists pip wheels, which must be vendored when the package is built: commit a built connectors/$file instead"

  # The commit that set this app_version, falling back to the one we're running on.
  commit=$(git log --format=%H -S"\"app_version\": \"$version\"" -- "$meta" | tail -1)
  commit=${commit:-$(git rev-parse HEAD)}
  # Reproducible archive: same source commit gives the same bytes and sha256.
  tar --sort=name --owner=0 --group=0 --numeric-owner \
      --mtime="@$(git log -1 --format=%ct "$commit")" \
      -cf - -C connectors/source "$app" | gzip -n > "$work/built/$file"
  built_at[$file]=$commit
  candidates+=("$file"$'\t'"$work/built/$file")
done

[ ${#candidates[@]} -gt 0 ] || { echo "No connector versions found"; exit 0; }

declare -A last_commit  # app -> commit that introduced its previous version

while IFS=$'\t' read -r file pkg; do
  app=${file%-v*.tgz}
  version=${file#"$app"-v}
  version=${version%.tgz}
  [[ $version =~ $VERSION_RE ]] || fail "$pkg: file name must be <app>-vX.Y.Z.tgz"
  tag="$app-v$version"

  # Tag the commit that introduced this version, not whatever HEAD is when we run.
  if [ -n "${built_at[$file]:-}" ]; then
    commit=${built_at[$file]}
  else
    commit=$(git log --diff-filter=A --format=%H -1 -- "$pkg")
    commit=${commit:-$(git rev-parse HEAD)}
  fi
  prev=${last_commit[$app]:-}
  last_commit[$app]=$commit

  if grep -qxF "$tag" <<<"$released"; then
    echo "skip $tag: already released"
    continue
  fi

  dir="$work/$tag"
  mkdir -p "$dir"
  tar xzf "$pkg" -C "$dir"
  meta="$dir/$app/$app.json"
  [ -f "$meta" ] || fail "$pkg: no $app/$app.json inside the package"
  embedded=$(jq -r .app_version "$meta")
  [ "$embedded" = "$version" ] || fail "$pkg: file name says $version but $app.json inside says $embedded"
  src="connectors/source/$app"
  if [ -z "${built_at[$file]:-}" ] && [ -f "$src/$app.json" ] \
      && [ "$(jq -r .app_version "$src/$app.json")" = "$version" ]; then
    diff -rq "$dir/$app" "$src" || fail "$pkg differs from $src: re-extract source/ or rebuild the package"
  fi

  (cd "$(dirname "$pkg")" && sha256sum "$file") > "$work/$file.sha256"

  if [ -n "$prev" ]; then
    changes=$(git log --format='- %s (%h)' "$prev..$commit" -- connectors/)
  else
    changes="Initial release of this package in this repository."
  fi
  origin=""
  if [ -n "${built_at[$file]:-}" ]; then
    origin="
This package was built by the release workflow from \`$src\` at ${commit:0:7}; no pre-built package was committed for this version."
  fi

  notes="$work/$tag.md"
  cat > "$notes" <<EOF
$(jq -r .description "$meta")

| | |
|---|---|
| Version | $version |
| Min SOAR version | $(jq -r .min_phantom_version "$meta") |
| Python | $(jq -r .python_version "$meta") |

Install with **Apps > Install App** in SOAR, uploading \`$file\`. SOAR only accepts a version strictly greater than the one installed. Verify the file after transfer with \`sha256sum -c $file.sha256\`.
$origin
### Changes
${changes:-No connector changes recorded.}
EOF

  title="$(jq -r .name "$meta") v$version"
  if [ "$DRY_RUN" = 1 ]; then
    echo "[dry-run] would publish '$title' as $tag at ${commit:0:7}"
    sed 's/^/    | /' "$notes"
  else
    gh release create "$tag" "$pkg" "$work/$file.sha256" \
      --target "$commit" --title "$title" --notes-file "$notes"
    echo "published $tag"
  fi
done < <(printf '%s\n' "${candidates[@]}" | sort -V)
