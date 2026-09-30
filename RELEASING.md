# Releasing a connector version

Each connector version gets its own GitHub Release, published automatically by
`.github/workflows/release-connectors.yml` when a push to `master` introduces a
version that has no release yet.

To ship a new version, bump `app_version` in `connectors/source/<app>/<app>.json`
and merge to `master`. That's it. The workflow builds `<app>-vX.Y.Z.tgz` from
`connectors/source/<app>/` and publishes it. SOAR only installs a strictly higher
version than the one it already has, so always bump.

If you'd rather ship your own build, commit it as `connectors/<app>-vX.Y.Z.tgz` in
the same merge as the version bump. A committed package always wins over building
from source. A connector whose JSON lists pip `wheel` dependencies needs this, since
the wheels have to be vendored when the package is built, so the workflow won't
build it for you. If you push the bump first and the package later, the release
already exists and keeps the workflow-built package.

Each release is tagged `<app>-vX.Y.Z` on the commit that introduced that version,
with the package and a `.sha256` attached. Versions that already have a release are
skipped, so to backfill older versions add their `.tgz` files to `connectors/` and
run the workflow (Actions > Release connectors > Run workflow).

The job refuses to publish a committed package whose embedded `app_version` doesn't
match its file name, or that differs from `connectors/source/<app>/` when that folder
is at the same version. `DRY_RUN=1 .github/scripts/release-connectors.sh` previews
a release locally (needs `gh` and `jq`).
