# Cleanup TODO

What is left to clean, decide or investigate. Background and rationale are in
[`docs/uc1_dev_notes.md`](docs/uc1_dev_notes.md). Nothing here is needed for the package to
work as shipped.

**Rules for any code item below**

- Playbook custom code exists twice, in the `.py` and in the JSON `userCode`. Change both, then
  rebuild the `.tgz` so it extracts identical to `playbooks/source/`.
- A connector change needs an `app_version` bump, a rebuilt `.tgz` and a matching
  `connectors/source/`. On merge to `master` the release workflow publishes that version
  automatically (see `RELEASING.md`), so batch the connector items into one version.

## 1. Fix before the next deployment

- [ ] **Document or template the `soar6` asset.** Two playbook blocks hard-code an asset named
  `soar6` (the Phantom app's own "self-ref" asset): `wait_before_recheck` (recheck handler,
  the `no op` wait) and `add_note_no_targets` (orchestrator). `assets/` has no template for it and
  `HANDOVER.md` has no install step, so on a target SOAR without an asset of that exact name
  those two blocks have nothing to run against. Either add `assets/<name>.json` plus an install step, or change the two blocks
  (`connectorConfigs` in the JSON and `assets=[...]` in the `.py`).
- [ ] **Rewrite the "no targets" operator note.** `format_no_targets_note` (orchestrator `.py`
  and the JSON node 11 `template`) still tells operators to set each asset's Description to
  `cyberark_ccp:safe=...`. Discovery has been driven by the `cyberark_ccp_rotation_state` custom
  list since 2026-08-03. Suggested replacement text:

  ```
  No rotation targets found in the 'cyberark_ccp_rotation_state' custom list for CyberArk credential rotation.

  Add one row per asset to manage, with at least these columns:

  - **asset** = SOAR asset name
  - **safe** = CyberArk safe containing the credential
  - **user_field** = asset config key that holds the username (e.g. 'username')
  - **pwd_field** = asset config key to update with the rotated password (e.g. 'password')
  - **address** = (optional) CyberArk address filter for accounts sharing the same username

  The status columns are filled in by the playbooks after the first run.
  ```

## 2. Investigate

- [ ] **Password-type fields on the `asset_update_configuration` write-back.** The original
  comment flags a known, unfixed risk on this path; the details were lost (the notes file it
  referred to was never exported). The plan doc separately records a `client_key` corruption on
  the CCP asset that recurred with no known cause. Nothing establishes a link; find out whether
  there is one, then record the answer in the dev notes.

## 3. Connector cleanup (one release, 1.0.29 → 1.0.30)

Needs a code change, so all of these ship together.

- [ ] Remove the 11 `self.save_progress("DEBUG GUI: ...")` lines in
  `cyberark_ccp_connector.py` (lines 96, 116, 161, 166, 175, 180, 189, 198, 207, 217, 302), or
  switch them to `self.debug_print`. They are visible in the action's progress output today, so
  this is a small behaviour change.
- [ ] Fix or drop the requirement tags in `cyberark_ccp_consts.py`: `DEFAULT_TIMEOUT ... # seconds (NFR6)`
  and `MAX_RETRIES ... # (NFR7)`. The plan doc defines NFR-6 as mTLS authentication and NFR-7 as
  idempotent deployment, so the tags point at the wrong requirements.
- [ ] Delete the unused `response` in `_handle_test_connectivity` (line 104, use `ret_val, _ =`)
  and the redundant `import json` inside `main()` (line 431; `json` is imported at line 4).
- [ ] Clean `connectors/source/cyberark_ccp/README.md`, which ships inside the package: the
  references to `tools/build.sh` and `config/soar_config.json` (neither is in this repo), and the
  `soar8` / "homelab" wording. Update its **Version** line with the bump.
- [ ] Decide on the package metadata in `cyberark_ccp.json`: `publisher` (`Ted`) and the stale
  `utctime_updated` (2026-04-13).
- [ ] Update `.gitleaksignore`. It pins the false positive by line number
  (`cyberark_ccp_connector.py:private-key:334`, the PEM marker list in `_normalize_pem`), and
  removing lines above it moves that line.

## 4. Documentation cleanup

- [ ] **`docs/uc1_implementation_plan.md` contradicts itself on discovery.** Context, "Key design
  decisions", the architecture table (row 4) and FR-2 still describe description-based discovery
  as current; the later "Discovery: custom list (current, since 2026-08-03)" section is the
  truth. Update the early sections.
- [ ] **The plan describes a custom function that isn't in the package.** `asset_list` (CF2,
  architecture row 5, FR-3, the `find_cyberark_asset` step in the pipeline) is called by no
  playbook and not shipped. Remove it from the plan or restore it.
- [ ] **Dangling references in the plan:** eight to `docs/next-steps.md` and one to
  `INSTALL.md`, neither in this package. Drop them or bring the content over.
- [ ] **Split history from reference.** The plan is a 600-line log: soar6-era ID tables, "Open
  Issues (as of 2026-04-08)", the superseded "Asset Description Convention", "Post-Build State".
  Move the historical parts to `docs/history/` and keep the plan to the current design and the
  setup guide.
- [ ] Keep `HANDOVER.md` and `HANDOVER_french.md` in step with any change above (both copies).

## 5. Tooling

- [ ] **CI check for the playbook packages.** The release workflow already guards the connector
  (package vs `source/`). Nothing guards the playbooks, and a JSON/`.py` desync has already
  happened (`6d7901f`; the orchestrator `update_severity` comment fixed in `26113ae`).
  A job that checks, per playbook, that every JSON `userCode` is verbatim in the `.py` and that
  each `.tgz` extracts identical to `source/` would catch both.

## Reviewed and deliberately kept

Looked at during the cleanup; not TODOs.

- **VPE scaffolding:** `Custom Code Start/End` banners, `phantom.debug("x() called")`, the long
  block signatures. Generated by the visual editor, which would put them back.
- **Constants repeated inside functions** (`MAX_RECHECK_ATTEMPTS`, `STATE_LIST_NAME`, ...): a SOAR
  Pylint constraint per the plan doc.
- **Duplicated severity mapping and state-list upsert** in the orchestrator and the recheck
  handler: they run in callback chains, where a custom function would race with `on_finish`.
- **`verify=False` on the playbooks' REST calls:** they target the SOAR instance they run on
  (`build_phantom_rest_url`). No change proposed; revisit if TLS policy requires it.
