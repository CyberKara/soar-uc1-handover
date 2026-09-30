#!/usr/bin/env bash
# Publish a GitHub Release for every connector package in connectors/ that
# doesn't have one yet. Idempotent: versions that already have a release are
# skipped, so dropping several older .tgz files into connectors/ backfills all
# of them in one run.
#
# Convention (same as the SOAR build output): connectors/<app>-v<X.Y.Z>.tgz
#   tag     <app>-v<X.Y.Z>, created on the commit that first added the .tgz
#   assets  the .tgz, plus a .sha256 to verify it after an air-gap transfer
#
# Before publishing, the package is checked for desync: the version inside it
# must match the file name, and (for the version currently in connectors/source/)
# the extracted contents must match source/.
#
# Needs gh (GH_TOKEN for auth, GH_REPO for the repo), jq, and full git history.
# DRY_RUN=1 prints what would be published without creating anything.
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"

fail() { echo "::error::$*"; exit 1; }

cd "$(git rev-parse --show-toplevel)"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

shopt -s nullglob
pkgs=(connectors/*-v*.tgz)
[ ${#pkgs[@]} -gt 0 ] || { echo "No connector packages in connectors/"; exit 0; }

released=$(gh release list --limit 1000 --json tagName --jq '.[].tagName')
declare -A last_commit  # app -> commit that introduced its previous version

while IFS= read -r pkg; do
  file=$(basename "$pkg")
  app=${file%-v*.tgz}
  version=${file#"$app"-v}
  version=${version%.tgz}
  [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "$pkg: file name must be <app>-vX.Y.Z.tgz"
  tag="$app-v$version"

  # Tag the commit that added this package, not whatever HEAD is when we run.
  commit=$(git log --diff-filter=A --format=%H -1 -- "$pkg")
  commit=${commit:-$(git rev-parse HEAD)}
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
  if [ -f "$src/$app.json" ] && [ "$(jq -r .app_version "$src/$app.json")" = "$version" ]; then
    diff -rq "$dir/$app" "$src" || fail "$pkg differs from $src: re-extract source/ or rebuild the package"
  fi

  (cd connectors && sha256sum "$file") > "$work/$file.sha256"

  if [ -n "$prev" ]; then
    changes=$(git log --format='- %s (%h)' "$prev..$commit" -- connectors/)
  else
    changes="Initial release of this package in this repository."
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
done < <(printf '%s\n' "${pkgs[@]}" | sort -V)
