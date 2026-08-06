# UC1 — Automated Credential Rotation — Air-Gapped Handover Package

Generated 2026-08-06 21:29 UTC from `credential_rotation` (source env: `soar8`).

This package is self-contained — everything needed to deploy this use case by hand
in an environment with no network access back to this repo or to `soar8`.

*(Version française : `HANDOVER_french.md` dans ce même dossier.)*

## Contents

| Path | What |
|------|------|
| `connectors/` | Connector app package(s): cyberark_ccp-v1.0.29.tgz |
| `connectors/source/` | Same connector(s), extracted — for reading, not for import |
| `playbooks/*.tgz` (CFs) | cyberark_asset_update_configuration, cyberark_asset_get_tagged_for_rotation |
| `playbooks/*.tgz` (PBs) | cyberark_credential_rotation, cyberark_rotation_orchestrator, cyberark_recheck_handler |
| `playbooks/source/` | Same CFs/playbooks, extracted — for reading, not for import |
| `assets/*.json` | Asset config templates (credentials redacted — see below) |
| `custom_lists/*.json` | Custom list schema (header row only — see Bootstrapping below) |
| `docs/` | Implementation plan doc, for full design context |

## Install order

1. **Install the connector app(s)** — Apps > Install App, upload each file in `connectors/`.
   (`connectors/source/` is the same code extracted for reading — don't import from there,
   the GUI needs the `.tgz`.)
2. **Configure assets from the templates in `assets/`** — Apps > Configure New Asset for
   each. Fields marked in a template's `redacted_fields` list are placeholders
   (`<<SET ME...>>`) — **you must fill these in yourself** from your own vault/CMDB; they
   were never exported with real values (SOAR encrypts `password`-type fields at rest and
   the export process cannot read them back in usable form even in principle).
3. **Create the custom list(s)** from `custom_lists/*.json` — each file has the exact
   `content` array (header row + data rows) to POST to `/rest/decided_list`:
   ```bash
   curl -sk -u '<user>:<password>' -X POST https://<target>:<port>/rest/decided_list \
     -H 'Content-Type: application/json' \
     -d @custom_lists/<list_name>.json
   ```
   (the file's top-level shape is `{"name": ..., "content": [...]}` — matches the REST
   payload directly.)
4. **Import custom functions, then playbooks** (in that order — playbooks reference CFs)
   from `playbooks/*.tgz`, via Apps/Playbooks > Import in the target SOAR GUI.
   (`playbooks/source/` is the same code extracted for reading — don't import from there,
   the GUI needs the `.tgz`.)
5. **Activate automation playbooks** and set their **Run As** user per the implementation
   plan doc's Setup Guide (see `docs/`).

## Bootstrapping the vault mapping (custom-list-driven discovery)

Discovery of what to rotate/act on is driven entirely by the custom list content you just
created — there is **no automatic discovery step**. A brand-new target only becomes visible
once you add a row for it. This is deliberate: mapping a SOAR asset to its vault
safe/account name requires knowledge only you have (which of your assets need a
vault-sourced credential, and what that credential is called in your vault) — nothing in
SOAR or the vault can infer this automatically.

For each asset you want this UC to manage, add a row to the relevant custom list with at
least its config columns populated (status/result columns can start blank — the playbooks
fill those in after the first real run).

**Column reference** (the exported `custom_lists/*.json` files contain the header row only —
deliberately no data rows, since this source environment's rows are its own lab/test assets,
not yours):

- `cyberark_ccp_rotation_state`: `asset, safe, user_field, pwd_field, address, connector, username, status, message, last_rotated, event_link`
  - Example row (illustrative only — replace every value): `<your-asset-name>, <example-safe>, <example-user_field>, <example-pwd_field>, <example-address>, <example-connector>, <example-username>, <example-status>, <example-message>, <example-last_rotated>, <example-event_link>`

See the copied implementation plan doc in `docs/` for the authoritative column semantics.

## Verification

After importing everything and activating automation playbooks, trigger one run manually
(e.g. the timer asset's manual poll, or per the implementation plan doc's trigger section)
and confirm: a container is created, the expected child playbook(s) run, and the custom
list(s) reflect a real result. Check `spawn.log`/`decided.log`/`actiond.log` on the target
SOAR host if anything doesn't fire as expected.

## What was deliberately NOT exported

- Real credential values for any `password`-type config field (see step 2 above).
- The source environment's actual rotation-target assets — those are lab-specific test
  assets, not your infrastructure. Follow the Bootstrapping section above instead.
- Anything not explicitly listed in Contents above.
