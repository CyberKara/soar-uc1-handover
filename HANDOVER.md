# UC1 — Automated Credential Rotation — Air-Gapped Handover Package

Generated 2026-10-22 23:45 UTC from `credential_rotation` (source env: `soar8`).

This package is self-contained — everything needed to deploy this use case by hand
in an environment with no network access back to this repo or to `soar8`.

*(Version française : `HANDOVER_french.md` dans ce même dossier.)*

## Contents

| Path | What |
|------|------|
| `connectors/` | Connector app package(s): cyberark_ccp-v1.0.30.tgz |
| `connectors/source/` | Same connector(s), extracted — for reading, not for import |
| `custom_functions/` | Custom function package(s): cyberark_ccp_get_targets, cyberark_ccp_classify_secrets, cyberark_ccp_update_asset, cyberark_ccp_start_tests, cyberark_ccp_report |
| `custom_functions/source/` | Same custom function(s), extracted — for reading, not for import |
| `playbooks/` | Playbook package(s): cyberark_credential_refresh |
| `playbooks/source/` | Same playbook(s), extracted — for reading, not for import |
| `assets/*.json` | Asset config templates (credentials redacted — see below) |
| `custom_lists/*.json` | Custom lists — the rows this package defines, never the source's data rows (see the custom-list section below) |
| `docs/` | Implementation plan doc, for full design context |

## [!] Upgrading over an earlier install — read this first

These apply only if this app is already installed on the target from a
previous package. On a completely fresh target, skip to Install order.

- **Connector 1.0.30, two asset re-points and shorter texts (2026-10-11).** Install connector v1.0.30 over the existing CyberArk CCP app (same identifier; the asset keeps its settings). Re-import the two custom functions and the three playbooks. The orchestrator's `add_note_no_targets` and the recheck handler's `wait_before_recheck` now run on the SOAR (Phantom) asset named `soar8` instead of `soar6`: re-point both blocks to your own SOAR asset in the VPE and save, or the no-targets note is never written and every recheck fails. `cyberark_recheck_handler` keeps its helpers in Global Custom Code, so a VPE save no longer breaks it, and `cyberark_credential_rotation` keeps sending the CyberArk `address` filter after a save. Keep the orchestrator and the recheck handler active, Run As your automation user. The implementation plan in `docs/` now describes the current design only, with a Setup Guide (`INSTALL.md` is gone).

- **One playbook replaces three (2026-10-22).** Deactivate, then delete `cyberark_rotation_orchestrator`, `cyberark_recheck_handler` and `cyberark_credential_rotation`, and the custom functions `cyberark_asset_get_tagged_for_rotation` and `cyberark_asset_update_configuration`. Import the five `cyberark_ccp_*` custom functions (publish them): the update now writes only the password field (the old one set every other password field of the target to `********`), and an unusable list row is reported. Import `cyberark_credential_refresh`; its `start_tests` block holds the `test_connectivity` switch (true). Create a role that copies Automation with Assets: Edit allowed, and an automation user with that role. In the VPE, set the playbook's Run As to that user (an import does not carry it), re-point `get_secrets` and `wait_for_tests` to your CyberArk CCP and SOAR assets, save, then activate it. The list, the label and the Timer asset stay; the status values changed (implementation plan). APPAP282E is now retried by the next Timer run, not after 5 minutes.

## Install order

1. **Install the connector app(s)** — Apps > Install App, upload each file in `connectors/`.
   (`connectors/source/` is the same code extracted for reading — don't import from there,
   the GUI needs the `.tgz`.)
2. **Configure assets from the templates in `assets/`** — Apps > Configure New Asset for
   each. Fields marked in a template's `redacted_fields` list are placeholders
   (`<<SET ME...>>`) — **you must fill these in yourself**; they were never exported
   with usable values. Two different reasons appear in that list, and each placeholder
   says which one applies:

   - **Secrets** (passwords, API keys, certificates/keys) — take these from your own
     vault/CMDB. SOAR encrypts `password`-type fields at rest, so the export process
     cannot read them back in usable form even in principle.
   - **Identities and addresses** (usernames, client/app ids, endpoint URLs) — these
     are not secret, but they belonged to the source environment and are meaningless
     here. Enter the values *your* target system expects. **An identity must match the
     credential you enter beside it** — a real password paired with a leftover username
     from the source environment authenticates as nothing and returns HTTP 401.

   **The playbooks ship pointed at the asset names below.** Either create your assets
   with these names, or keep your own names and re-point each playbook's action blocks
   to your assets in the VPE, then save: every playbook in this package is built to
   survive a save. (A save makes a manually-run playbook available on every container
   label; re-importing it restores the label.)

   | Asset name | App | Used by | Template |
   |---|---|---|---|
   | `cyberark ccp mock` | CyberArk CCP | `cyberark_credential_refresh` | `assets/cyberark_ccp_mock.json` |
   | `soar8` | Phantom | `cyberark_credential_refresh` | `assets/soar8.json` |

3. **Create the custom list(s)** from `custom_lists/*.json` — each file has the exact
   `content` array (the rows this package defines — never the source's data rows) to POST to `/rest/decided_list`:
   ```bash
   curl -sk -u '<user>:<password>' -X POST https://<target>:<port>/rest/decided_list \
     -H 'Content-Type: application/json' \
     -d @custom_lists/<list_name>.json
   ```
   (the file's top-level shape is `{"name": ..., "content": [...]}` — matches the REST
   payload directly.)
4. **Import the custom functions, then the playbooks** (in that order — playbooks reference
   CFs). Each kind goes through its own importer:
   - **Custom functions** — every `custom_functions/*.tgz`: on the Custom Functions tab of the
     Playbooks page, the upload button whose tooltip reads *Import Custom Function*. The playbook
     importer rejects a CF archive ("failed to identify the import as a playbook").
     If the CF shows as a draft afterwards, open it in the editor and save it.
   - **Playbooks** — every `playbooks/*.tgz`: *Import Playbook* on the Playbooks page.
   (`custom_functions/source/` and `playbooks/source/` are the same code extracted for reading —
   don't import from there, the GUI needs the `.tgz`.)
5. **Activate automation playbooks** (`cyberark_credential_refresh`) and set their **Run As** user per the
   implementation plan doc's Setup Guide (see `docs/`).

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

1. **Test Connectivity** on the CyberArk CCP asset: it reads `test_safe` / `test_username` through CCP. Then add one row to `cyberark_ccp_rotation_state` for a TEST asset, columns `asset`, `safe`, `user_field`, `pwd_field` and `address` filled (the implementation plan's Data model).

2. **Run it:** Poll Now on the Timer asset `cyberark_ccp`, or wait for its daily run. Expect one container labelled `cyberark_ccp`, one run of `cyberark_credential_refresh` as its Run As user, one note, and the row's `status` `success` (written, test connectivity passed). `written (test failed)`: the password was written but the asset's own test failed. `pending`: CyberArk answered APPAP282E, the next run retries. `failed` gives CyberArk's message, `Asset not found`, or `not authorized to edit assets` (the Run As user's role lacks Assets: Edit).

If nothing fires, check the playbook is active with its Run As set, then `spawn.log`/`decided.log`/`actiond.log` on the SOAR host.

## What was deliberately NOT exported

- Real credential values for any `password`-type config field (see step 2 above).
- The source environment's own target assets and any custom-list rows — those are
  lab-specific test data, not your infrastructure. See the custom-list section above.
- Anything not explicitly listed in Contents above.
