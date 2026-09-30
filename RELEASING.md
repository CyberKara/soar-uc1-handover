# Releasing a connector version

Every `connectors/<app>-vX.Y.Z.tgz` on `master` gets its own GitHub Release,
published by `.github/workflows/release-connectors.yml`.

To ship a new version:

1. Bump `app_version` in the connector, build the package, and put it in
   `connectors/` as `<app>-vX.Y.Z.tgz` (SOAR only installs a strictly higher version).
2. Re-extract it into `connectors/source/<app>/` so the readable copy matches.
3. Merge to `master`.

The release is tagged `<app>-vX.Y.Z` on the commit that added the `.tgz`, with the
package and a `.sha256` attached. Versions that already have a release are skipped,
so to backfill older versions just add their `.tgz` files to `connectors/` and run
the workflow (Actions > Release connectors > Run workflow).

The job refuses to publish a package whose embedded `app_version` doesn't match its
file name, or that differs from `connectors/source/<app>/` when that folder is at the
same version. `DRY_RUN=1 .github/scripts/release-connectors.sh` previews a release
locally (needs `gh` and `jq`).
