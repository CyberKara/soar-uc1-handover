# Automated Credential Rotation (UC1) — Playbook Implementation Plan

**Status:** [x] planned | [x] built | [x] E2E validated | [x] code review fixes | [x] VPE polish | [x] released v5.1 (2026-04-17, clean-slate redeploy container 793)

> **soar8 note (2026-08-01):** this doc's IDs/asset table below (`soar6.karabox.cc:9443`) are the
> original soar6-era build. Playbooks were carried over to soar8 as-is during the migration and
> were **silently failing on every timer-fired run since at least 2026-07-21** due to a corrupted
> `client_key` on the CyberArk CCP asset (`password`-type config fields don't survive the
> soar6→soar8 migration — see `docs/next-steps.md` §43 for the full investigation/fix). Fixed and
> verified working end-to-end on soar8 2026-08-01. A follow-up static code review of the playbook
> Python then found + fixed 9 real bugs (§44) — redeployed same day, new soar8 IDs:
> `credential_rotation`=196, `cyberark_rotation_orchestrator`=197, `cyberark_recheck_handler`=198,
> CFs `cyberark_asset_update_configuration`=48 / `cyberark_asset_get_tagged_for_rotation`=49
> (superseding the migration-era 169-171/475-476 ids below). `f5_api_test`'s empty description on
> soar8 was also fixed 2026-08-01 (re-set via read-merge-write POST) — verified live, all four
> originally-validated targets (f5_api_test, splunk_primary, splunk_dr, app_server_test) now rotate
> correctly, matching the original v5.1 E2E outcome exactly. See `docs/next-steps.md` §43.
>
> **soar8 note (2026-08-03):** discovery mechanism changed from description-field parsing to
> reading vault-mapping columns out of `cyberark_ccp_rotation_state` — briefly a separate
> `cyberark_ccp_vault_mapping` list, then merged into the pre-existing status list the same day
> (its 5 columns were a strict subset, and the orchestrator already round-tripped those exact
> values every run) — column order reorganized config-first. UC1's `python_version` bumped
> 3.9→3.13, all 6 UC1 assets tagged `cyberark_ccp`. New ids: `credential_rotation`=202,
> `cyberark_rotation_orchestrator`=203, `cyberark_recheck_handler`=204, CFs
> `cyberark_asset_update_configuration`=52 / `cyberark_asset_get_tagged_for_rotation`=53.
> **[!] Also found the client_key corruption from 2026-08-01 had recurred independently** (not
> caused by these changes — confirmed via container history) sometime within a single day, no
> known trigger. Re-fixed and verified again, but the root cause of the *recurrence* is still
> unknown — treat as not durable until investigated. See
> `docs/next-steps.md` §45.
>
> **soar8 note (2026-08-03, later same day):** the `credential_rotation` playbook (the one PB in
> this UC missing the `cyberark_` prefix its two siblings already had) renamed to
> `cyberark_credential_rotation` — `.py`/`.json` files, both `phantom.playbook()` dispatch call
> sites (including their embedded JSON `userCode` mirrors), and every prose/comment reference
> updated. Current soar8 ids: `cyberark_credential_rotation`=205 (v1 — a new playbook object, not
> an in-place rename), `cyberark_rotation_orchestrator`=206, `cyberark_recheck_handler`=207, CFs
> unchanged at 52/53. Verified live via the REST `child_playbook_name` field on an actual dispatch,
> confirming the renamed playbook is really what's running. The old `credential_rotation` (id=202)
> was cleaned up via the SOAR web UI (REST deletion isn't available for playbooks — `405` on
> `DELETE`; GUI deletion is a soft-delete, `disabled: true`, row persists for audit history but is
> hidden from listings). See `docs/next-steps.md` §45.

## Release history

- **v5.1** (2026-04-17) — post-review cleanup: deleted dead CFs `cyberark_build_summary` / `cyberark_update_rotation_state`, normalized node-3 userCode tail to implicit style, rewrote INSTALL.md. E2E on clean-slate redeploy (container 793) ✓.
- **v5** — VPE polish pass: fixed `utility → decision` render bug, `connectorConfigs` yellow triangles, `inputParameters` datapath validation, missing `data.advanced.join: []`.
- **v4.3–v4.5** — iterative code-review fixes (JSON/Python sync, VPE correctness, input-parameter validation).
- **v4.1** — single-timer + artifact-based recheck consolidation.

---

## Context

First use case. SOAR assets (F5, Splunk, app servers, etc.) hold credentials that must be periodically
rotated from CyberArk CCP vault. Manual rotation is error-prone at scale. The automation discovers rotation
targets by reading asset descriptions, fetches fresh passwords from CyberArk via AppID + mTLS, updates the asset
configuration via read-merge-write, and verifies connectivity — on a recurring timer schedule.

**Business problem:** Each asset stores a credential in its configuration. When CyberArk rotates the vault
password, SOAR assets become stale. Without automation, the SOC must manually update every asset. At 10+
assets this becomes a reliability risk.

**Key design decisions:**
- Description-based discovery: no hardcoded asset lists; any SOAR asset becomes a rotation target by setting its description
- Single-timer + artifact-based recheck: main timer (24h, full rotation); APPAP282E → "Recheck Request" artifact → cyberark_recheck_handler wakes after 5 min
- State list as operator dashboard
- mTLS authentication to CyberArk — no username/password

---

## Architecture (v4 — current)

| # | Component | Type | Trigger | Scope |
|---|-----------|------|---------|-------|
| 1 | `cyberark_rotation_orchestrator` | automation PB | Container created, label=`cyberark_ccp` | Discover targets → dispatch → summarize |
| 2 | `cyberark_credential_rotation` | data PB | Dispatched by orchestrator or recheck handler | Rotate one asset's credential |
| 3 | `cyberark_recheck_handler` | automation PB | Artifact created, label=`cyberark_ccp` | Wait 5 min → retry cyberark_credential_rotation, max 3 attempts |
| 4 | `asset_get_tagged_for_rotation` | custom function | Called by orchestrator | Discover rotation targets by description |
| 5 | `asset_list` | custom function | Called by orchestrator | Find active CyberArk connector asset |
| 6 | `asset_update_configuration` | custom function | Called by `cyberark_credential_rotation` | Read-merge-write asset config update |

**Pipeline:**
```
Timer asset (label: cyberark_ccp, interval: 1440min)
  → creates container on label cyberark_ccp
    → cyberark_rotation_orchestrator (automation PB)
        on_start guard: skips if container has "Recheck Request" artifact
        discover_targets → asset_get_tagged_for_rotation CF → N targets
        find_cyberark_asset → asset_list CF
        check_targets / find_cyberark_asset (no targets or no vault → note + exit)
        dispatch_rotations: async phantom.playbook() × N targets
          → cyberark_credential_rotation (data PB) per target:
              [Action] get_secret_from_vault → CyberArk CCP asset
              [Code]   build_config_update — parse response, detect APPAP282E flag
              [Decision] update_decision — credential ready vs error
                YES → [Utility] update_target_asset (asset_update_configuration CF)
                      [Code]    run_test_connectivity — check CF result, test connectivity
                      [Code]    process_test_result — set status
                      [Code]    on_finish — save_playbook_output_data + create "Recheck Request"
                                           artifact if APPAP282E (run_automation=True)
                NO  → [Code]    format_error — pending_recheck or failed
                      [Code]    on_finish — save_playbook_output_data + create "Recheck Request"
                                           artifact if pending_recheck
        collect_results (counter callback) → build_summary
          → add_summary_note (phantom.add_note — synchronous)
          → update_rotation_state (phantom.set_list — synchronous)
          → update_severity (phantom.set_severity — synchronous)

    → cyberark_recheck_handler (automation PB, fires on artifact_created)
        on_start guard: skips if no "Recheck Request" artifact
        guard: skips if attempt > MAX_RECHECK_ATTEMPTS (3)
        wait_before_recheck: "no op" action, sleep_seconds=300
        dispatch_recheck: phantom.playbook("cyberark_credential_rotation")
        process_recheck_result: read child output, update state list, add note
          - success → "Recheck Succeeded" note
          - still pending → create new "Recheck Request" artifact (attempt+1)
          - failed → "Recheck Failed" note
          - max attempts → "Recheck Failed - Max Attempts" note
```

**v4.3 vs v4 changes (code review fixes, 2026-04-10):**
- Fixed: `credential_rotation.json` on_finish userCode removed stale `process_test_result:output` reference (dead code from removed block)
- Fixed: `credential_rotation.py` `update_decision` comparison changed from `== None` to `== ""` to match JSON VPE condition and `""` initialization
- Fixed: `cyberark_recheck_handler` severity update changed from `phantom.session_post()` to `phantom.set_severity()` (consistent with orchestrator, uses synchronous platform API)
- Fixed: `cyberark_recheck_handler.json` removed duplicate `####` markers in userCode blocks (nodes 2, 5)
- Fixed: `credential_rotation.json` `format_error` block added `inputParameters` for VPE data dependency visualization
- Fixed: Removed redundant module-level constants from `.py` files; all constants now defined inside the functions that use them per SOAR Pylint constraint

**v4 vs v3 changes:**
- Eliminated `cyberark_rotation_trigger` (merged into orchestrator on_start guard)
- Eliminated dual-timer (`cyberark_ccp_recheck` timer now disabled)
- Replaced recheck timer with artifact-based recheck (`cyberark_recheck_handler`)
- Renamed `cyberark_ccp_scheduler` → `cyberark_rotation_orchestrator`
- `credential_rotation.on_finish` now creates "Recheck Request" artifact on APPAP282E
- VPE fully connected: action→code→decision→utility→code flow, all blocks visible

**Design rationale — artifact-based recheck vs dual-timer:**
A second timer at 30 min means all pending assets wait up to 30 min regardless of when APPAP282E
was detected. Artifact-based recheck starts the 5-min clock immediately on detection.
The `run_automation=True` flag on `phantom.add_artifact` triggers `cyberark_recheck_handler`
automatically. The `playbook_trigger=artifact_created` setting fires on both container and artifact
creation — the `on_start` guard (check for "Recheck Request" artifact) is what routes correctly.

---

## Known Limitations / Out of Scope

| Item | Reason | Future path |
|------|--------|-------------|
| Real CyberArk vault URL | Dev uses mock at `127.0.0.1:8443` | Update `base_url` in CyberArk CCP asset for production |
| Real mTLS cert/key | Dev uses self-signed cert | Replace cert/key fields on CyberArk CCP asset in production |
| Rotation history | State list only stores current status per asset | Future: append to audit log list |
| Notification on failure | Summary note exists; no email/Slack alert | Future: add notification action to build_summary |

---

## Open Issues (as of 2026-04-08, E2E container 755)

| # | Issue | Symptom | Root Cause | Fix | Status |
|---|-------|---------|------------|-----|--------|
| 1 | Old playbook versions stay active after deploy | Double runs on same container, duplicate notes, state list overwrites | `import_playbook` creates a new ID; old versions remain active | `deploy.py` now auto-deactivates old versions after each import. | **FIXED** (v19, 2026-04-08) |
| 2 | `run_test_connectivity` uses wrong target_asset source | f5_api_test and app_server_test: "Playbook completed without result"; `test connectivity` never fires | `target_asset = update_result[0][1]` reads CF `asset_name` output which is empty. Also: VPE edge race — async `phantom.act()` callback fires after `on_finish`. Also: `address` param never sent to CyberArk (missing from `get_secret` parameters). | Read `target_asset` from `playbook_input:target_asset`. Replaced async `phantom.act()` with synchronous REST-based test connectivity (poll `POST/GET /rest/action_run`). Added `address` param to `get_secret_from_vault`. Merged `process_test_result` into `run_test_connectivity`, removed VPE node 11. | **FIXED** (v22, 2026-04-08) |
| 3 | Splunk assets fail with "Validation Error: Add username/address filter" | splunk_primary / splunk_dr always fail | Mock had entries but `get_secret_from_vault` never sent `address` parameter. | Fixed in issue #2 — `address` param now sent from `playbook_input:address`. | **FIXED** (v22, 2026-04-08) |
| 4 | Orchestrator summary note and state list not updating | No notes on container, state list stale | `add_summary_note` uses async `phantom.act("add note", assets=["soar6"])` inside a callback chain. After the last `collect_results` callback returns, VPE sees no pending nodes → fires `on_finish` before the async action executes. Same root cause as `feedback_vpe_async_race.md`. Evidence: container 762 has zero "add note" action_runs from orchestrator; on_finish fires 28ms after last callback. | Replace `phantom.act("add note")` with synchronous `phantom.add_note()`. Replace `phantom.custom_function("community/container_update")` with synchronous `phantom.set_severity()`. Collapse post-collection chain into synchronous code. | **FIXED** (v24, 2026-04-09) |

---

## Pre-conditions

**SOAR apps installed:**
- [x] Timer app (app id=149)
- [x] CyberArk CCP connector (app id=21 mock, prod: configure)
- [x] Target connectors (F5 id=12, Splunk id=23/24, Phantom self-ref id=123)

**Labels:**
- [x] `cyberark_ccp` label exists in SOAR Event Settings

**Assets configured:**
- [x] CyberArk CCP mock asset (id=21): `base_url=https://127.0.0.1:8443`
- [x] Main timer asset `cyberark_ccp` (id=22): label=`cyberark_ccp`, interval=1440min, polling enabled
- [x] `cyberark_ccp_recheck` (id=26): **DISABLED** — recheck is now artifact-based
- [x] Target assets with description set (see [Asset Description Convention](#asset-description-convention))

**Custom lists:**
- [x] `cyberark_ccp_rotation_state` (11 columns, see below)

**Dev SOAR asset IDs (soar6.karabox.cc:9443):**

| Asset | ID | Notes |
|-------|----|-------|
| `cyberark_ccp` (timer) | 22 | main timer, 1440min |
| `cyberark_ccp_recheck` (timer) | 26 | disabled in v4 |
| CyberArk CCP mock | 21 | base_url=https://127.0.0.1:8443 |
| `f5_api_test` | 12 | description: `cyberark_ccp:safe=F5Safe,user_field=username,pwd_field=password,address=f5.internal.lab` |
| `splunk_primary` | 23 | description: TestSafe, address=splunk.internal.lab |
| `splunk_dr` | 24 | description: TestSafe, address=splunk-dr.internal.lab |
| `app_server_test` | 25 | description: TestSafe/svc_rotating — used for APPAP282E testing |
| `soar6` (Phantom self-ref) | 14 | points to `<redacted-lab-internal-ip>:9443` — used for "no op" wait in recheck handler |

---

## PB1: `cyberark_rotation_orchestrator` (automation)

**Status:** [x] built | [x] deployed (id=719, v28, active) | issue #4 fixed — async→sync platform APIs

**Inputs:** none (discovers everything at runtime)
**Output:** none (writes notes + upserts state list)

**Flow:**
```
on_start (guard: skip if Recheck Request artifact present)
  → discover_targets (CF: asset_get_tagged_for_rotation)
  → read_discover_result (bridge code block)
  → check_targets → [decision] no targets → format_no_targets_note → add_note_no_targets
  → dispatch_rotations (loop: phantom.playbook × N, callback=collect_results)
  → collect_results (counter callback, N calls → proceed on last)
  → build_summary
  → add_summary_note (phantom.add_note — synchronous, no connector)
  → update_rotation_state (phantom.set_list — synchronous)
  → update_severity (phantom.set_severity — synchronous)
```

**Node table:**
| Step | Type | Name | Purpose |
|------|------|------|---------|
| 1 | start | `on_start` | Guard: collect artifacts, skip if "Recheck Request" present |
| 2 | utility | `discover_targets` | Call `asset_get_tagged_for_rotation` CF |
| 3 | code | `read_discover_result` | Bridge block: reads utility result (avoids utility→decision VPE rendering bug) |
| 4 | decision | `check_targets` | `total_count > 0` → dispatch path; else → no targets note |
| 5 | code | `dispatch_rotations` | Loop: async `phantom.playbook("cyberark_credential_rotation", callback=collect_results)` per target. Save expected count. |
| 6 | code | `collect_results` | Counter callback. Guard: `if results is None: return`. Counts completed children via REST. On last child → chain to build_summary. |
| 7 | code | `build_summary` | Guard: `if completed < total: return`. Builds markdown note, computes severity. |
| 8 | code | `add_summary_note` | `phantom.add_note()` — synchronous platform API, no connector action needed. Chains to update_rotation_state. |
| 9 | code | `update_rotation_state` | Read-merge-write `cyberark_ccp_rotation_state` custom list via `phantom.set_list()`. Chains to update_severity. |
| 10 | code | `update_severity` | `phantom.set_severity()` — synchronous platform API. |
| 11 | format | `format_no_targets_note` | Description convention instructions template |
| 12 | action | `add_note_no_targets` | `add note` via soar6 asset (static asset — acceptable for no-targets path) |

**Block inventory:** 1 action · 0 prompt · 1 decision · 7 code · 1 utility · 1 format

**Why code blocks for post-collection chain:** Counter-join for dynamic N children requires Python. VPE has no native "join N dynamic children" block. Post-collection operations (note, state list, severity) use synchronous platform APIs (`phantom.add_note`, `phantom.set_list`, `phantom.set_severity`) to avoid the VPE async callback race — `phantom.act()` in callback context fires on_finish before the action executes.

**SOAR trigger gotcha:** `playbook_trigger=artifact_created` fires on BOTH container and artifact creation. The `on_start` guard (check for "Recheck Request" artifact) is the actual routing mechanism — not the trigger setting.

---

## PB2: `cyberark_credential_rotation` (data)

**Renamed 2026-08-03** from `credential_rotation` for prefix consistency with its two
siblings (`cyberark_rotation_orchestrator`, `cyberark_recheck_handler`) — see
`docs/next-steps.md` §45.

**Status:** [x] built | [x] deployed (soar8 id=196, v2, 2026-08-01) | issues #2 and #3 fixed

**Inputs:** `target_asset`, `safe`, `username`, `config_field`, `address` (optional)
**Output:** `{"status": "...", "message": "...", "target_asset": "...", "cyberark_safe": "...", "cyberark_username": "...", "password_change_in_process": bool, "timestamp": "..."}`

**Flow (updated 2026-08-01 — added `validate_inputs`, see `docs/next-steps.md` §44):**
```
on_start
  → [Decision] validate_inputs — safe/username both present (native, JSON node "10")
       NO  → [Code] format_error (reuses the rotation_error run_data fallback)
       YES → [Action]   get_secret_from_vault — phantom.act("get secret") on CyberArk CCP asset
             [Code]     build_config_update — parse response, detect APPAP282E/password_change_in_process
             [Decision] update_decision — credential ready (error==None) vs error
                  YES → [Utility] update_target_asset — asset_update_configuration CF
                        [Code]    run_test_connectivity — check CF result, then synchronous REST
                                  POST /rest/action_run "test connectivity" on dynamic target asset + poll
                  NO  → [Code]    format_error — APPAP282E → pending_recheck; else failed
  → on_finish — save_playbook_output_data; create "Recheck Request" artifact if pending_recheck
```

**Node table:**
| Step | Type | Name | Purpose |
|------|------|------|---------|
| 1 | start | `on_start` | Calls `validate_inputs`. |
| 10 | decision | `validate_inputs` | **Added 2026-08-01.** Native decision: `playbook_input:safe`/`username` both `!= ""`. Replaces a hand-written `.py`-only guard that had no JSON representation — see §44 finding 1 (a GUI resave would have silently deleted it). |
| 2 | action | `get_secret_from_vault` | `phantom.act("get secret")`. Params: safe, username, address (optional). Now a clean native-action passthrough — validation moved to node 10. |
| 3 | code | `build_config_update` | Parse CyberArk result. Set `config_json`, `error`, `password_change_in_process`. Save to run_data. Output vars now initialized before the Custom Code marker (§44). |
| 4 | decision | `update_decision` | `error == None` → YES path. Else path. |
| 5 | utility | `update_target_asset` | `asset_update_configuration` CF. Inputs from `build_config_update` run_data. |
| 6 | code | `run_test_connectivity` | Check CF result (fail → save error + return). Then synchronous REST `POST /rest/action_run` + polling for `test connectivity` on dynamic target asset. **Exception to "no phantom.act in code blocks" rule:** native VPE action blocks require a static asset; test connectivity must target a runtime-determined asset. Uses REST action_run pattern from `feedback_vpe_async_race.md`. |
| 8 | code | `format_error` | Read error from run_data. APPAP282E → `pending_recheck`. Else → `failed`. Save to `format_result:output`. |
| — | end | `on_finish` | Read `format_result:output`. `phantom.save_playbook_output_data()`. Create "Recheck Request" artifact if `password_change_in_process` or `pending_recheck`. |

**Block inventory:** 1 action · 0 prompt · 2 decision · 3 code · 1 utility

**Critical — `run_test_connectivity` target_asset source:**
Must use `playbook_input:target_asset`, NOT `update_result[0][1]` (CF `asset_name` output is empty).

**Why synchronous REST for test connectivity (exception to "no phantom.act in code blocks"):**
Native VPE action blocks require a static asset selected at design time. `test connectivity` must target a runtime-determined asset (f5_api_test, splunk_primary, etc.). Uses synchronous REST `POST /rest/action_run` + polling pattern from `feedback_vpe_async_race.md`. This is the ONE legitimate use of REST action_run in UC1.

**Why CyberArk failure = no asset update:**
`format_error` skips `update_target_asset` entirely. Writing a stale credential would break connectivity immediately.

---

## PB3: `cyberark_recheck_handler` (automation)

**Status:** [x] built | [x] deployed (id=705, v23, active) | APPAP282E detection validated (container 759)

**Inputs:** none (reads from "Recheck Request" artifact CEF fields)
**Output:** none (writes notes, updates state list, creates next artifact if still pending)

**Flow:**
```
on_start
  → check_recheck_artifact (code):
      collect artifacts → find most recent "Recheck Request" by highest id
      guard: no artifact → skip
      guard: attempt > MAX_RECHECK_ATTEMPTS (3) → note + stop
      save recheck context to run_data
  → wait_before_recheck: phantom.act("no op", sleep_seconds=300, assets=["soar6"])
  → dispatch_recheck (code):
      read run_data → build inputs → phantom.playbook("cyberark_credential_rotation", callback=process_recheck_result)
  → process_recheck_result (code):
      guard: if results is None: return
      read child output via REST (playbook_run query)
      update state list
      status == success → "Recheck Succeeded" note
      still pending → create new "Recheck Request" artifact (attempt+1, run_automation=True)
      max attempts → "Recheck Failed - Max Attempts" note
      failed → "Recheck Failed" note
      re-evaluate container severity from state list (all success→low, any failed→high, any pending→medium)
```

**CEF fields on "Recheck Request" artifact:**
| Field | Label | Content |
|-------|-------|---------|
| `cs1` | target_asset | Asset name |
| `cn1` | attempt | Attempt number (1-indexed) |
| `cs2` | rotation_params | JSON: `{safe, username, address, config_field}` |

**Bounded retry:** MAX_RECHECK_ATTEMPTS = 3. Each recheck creates a new artifact with `cn1 = attempt+1`. Guard in `check_recheck_artifact` stops if `attempt > 3`.

---

## CF1: `asset_get_tagged_for_rotation`

**Status:** [x] deployed (soar8 id=53, v2, 2026-08-03) — rewritten, see `docs/next-steps.md` §45

**Inputs:** `list_name` (string, default `"cyberark_ccp_rotation_state"`)
**Outputs:** `asset_name`, `asset_id`, `safe`, `username`, `user_field`, `pwd_field`, `address`, `app_name`, `total_count`

**Rewritten 2026-08-03** to read vault-mapping columns (1-5) out of the `cyberark_ccp_rotation_state`
list instead of parsing free-text asset descriptions (see "Discovery: custom list" below — the old
"Asset Description Convention" section is superseded and kept only as historical record). Briefly a
separate `cyberark_ccp_vault_mapping` list, merged into `cyberark_ccp_rotation_state` the same day
— see "Custom Lists" below for the merged column layout. For each list row, looks up
the named asset via `GET /rest/asset?_filter_name=...` (skips stale rows pointing at a
renamed/deleted asset), reads `user_field` from the asset config to get the actual username,
resolves `app_name` from the app_id via `GET /rest/app/{app_id}`. `description_raw` output dropped
(was never consumed downstream).

**Key gotcha:** `app_name` field on assets is empty in automation context — must resolve via `GET /rest/app/{app_id}`.

---

## CF2: `asset_list`

**Status:** [x] deployed (id=475, published)

**Inputs:** `app_name` (optional), `asset_name` (optional), `tags` (optional), `exclude_disabled` (bool)
**Outputs:** `id`, `name`, `app_name`, `disabled`, `total_count`

Used by the orchestrator to find the active CyberArk CCP asset by name (`asset_name` filter, not `app_name`).

---

## CF3: `asset_update_configuration`

**Status:** [x] deployed (id=476, published)

**Inputs:** `asset` (asset name or id), `configuration_updates` (JSON string of fields to update)
**Outputs:** `success`, `asset_id`, `asset_name`, `message`

Read-merge-write: `GET /rest/asset/{id}` → merge updates → `POST /rest/asset/{id}` with full payload
including `name`, `tags`, `description`, `configuration`. Omitting any field from POST silently resets it.

**Critical:** Must include `description` in write-back — rotation targets are discovered via description.
Omitting it wipes the description after first rotation, removing the asset from all future runs.

---

## Discovery: custom list (current, since 2026-08-03)

Rotation targets are defined by the vault-mapping columns (1-5) of the `cyberark_ccp_rotation_state`
custom list — see "Custom Lists" below. Each row maps one asset name to its CyberArk safe/field
mapping *and* carries that asset's last rotation status — one list, two roles (merged same day from
a briefly-separate `cyberark_ccp_vault_mapping` list once it became clear the columns were a strict
subset already round-tripped by the orchestrator every run). This replaced the description-field
convention below because the free-text `description` field had zero schema enforcement and was
exactly what let one target's mapping silently go missing after the soar6→soar8 migration
(`docs/next-steps.md` §43) — a structured list gives one place to see/manage every mapping instead
of opening each asset individually, and removes the fragile key=value string parsing entirely.
Onboarding a brand-new target now means adding a row to `cyberark_ccp_rotation_state` with the 5
config columns populated (status columns can start blank) before its first rotation runs.
UC1-target assets are also now tagged `cyberark_ccp` for at-a-glance visibility in the Assets list
(tags are NOT used for discovery — see below for why).

## Asset Description Convention (superseded 2026-08-03 — historical record only)

Target SOAR assets used to need this string in their **description** field; no longer required —
kept here as historical record and because target assets' descriptions were left in place (inert,
harmless) rather than cleaned up:
```
cyberark_ccp:safe=My-Safe,user_field=username,pwd_field=password[,address=myhost.example.com]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `safe` | Yes | CyberArk safe name (hyphens allowed — no tag character restrictions) |
| `user_field` | Yes | Config field on the asset holding the CyberArk username |
| `pwd_field` | Yes | Config field to update with the rotated password |
| `address` | No | Disambiguates accounts with same username in same safe |

**Why description instead of tags (original 2026-04 rationale — tags still aren't used for
discovery, this just explains the historical choice):** SOAR tags reject hyphens in values (e.g.
`safe=My-Safe`). Description has no restrictions. A custom list sidesteps this same constraint
differently — hyphens in a list cell are fine, it's specifically *tag values* that reject them.

---

## Custom Lists

| List | Columns | Purpose |
|------|---------|---------|
| `cyberark_ccp_rotation_state` | asset, safe, user_field, pwd_field, address, connector, username, status, message, last_rotated, event_link | **Merged 2026-08-03** — serves two roles in one list. Columns 1-5 (config-first) are the discovery input, read by `asset_get_tagged_for_rotation`; columns 6-11 are the status output, written by `update_rotation_state`/`process_recheck_result`. Was briefly two separate lists (a short-lived `cyberark_ccp_vault_mapping` for columns 1-5 existed for a few hours the same day) before merging once it was clear columns 1-5 were already a subset the orchestrator round-tripped every run anyway. Column order was reorganized (config columns first, contiguous) from the original interleaved layout as part of the merge — any code reading this list by positional index needed updating; three touch points found via grep (the CF, `update_rotation_state`, `process_recheck_result` + its severity re-evaluation). |

**Status values:**

| Status | Meaning |
|--------|---------|
| `success` | Credential rotated and connectivity verified |
| `rotated (connectivity failed)` | Credential updated but connectivity test failed |
| `rotated (no test result)` | Credential updated but no connectivity result available |
| `rotated (change pending)` | Updated with current password; CyberArk change in progress |
| `pending_recheck` | CyberArk APPAP282E; recheck handler will retry |
| `failed` | Rotation failed entirely |

---

## Setup Guide

### Step 1 — Create Label

Administration → Event Settings → Labels → **Add Label**: `cyberark_ccp`

### Step 2 — Create Automation User

Administration → User Management → **Add User**
- Username: `automation_cyberark_ccp`
- Type: Automation
- Roles: **Admin** (required — Asset Owner alone insufficient for asset config writes via REST in automation context)

### Step 3 — Install CyberArk CCP Connector

Apps → Install App → upload `cyberark_ccp.tgz` (built from `soar-connectors/connectors/cyberark_ccp/`
— the canonical connector home; not this repo)

### Step 4 — Configure CyberArk CCP Asset

Apps → CyberArk CCP → **Configure New Asset**
- Asset name: `cyberark_ccp`
- `base_url`: CyberArk CCP REST endpoint
- `app_id`: CyberArk Application ID
- `client_cert` / `client_key`: PEM-encoded mTLS cert/key
- `verify_ssl`: `true` for production

### Step 5 — Configure Timer Asset

Apps → Timer → **Configure New Asset** (one timer):
- Asset name: `cyberark_ccp`
- Label: `cyberark_ccp`, interval: `1440` min

**Note:** No recheck timer needed in v4. Recheck is artifact-based.

### Step 6 — Create Custom List

```bash
curl -sk -H "ph-auth-token: <TOKEN>" \
  -X POST https://<SOAR_HOST>:<SOAR_PORT>/rest/decided_list \
  -H "Content-Type: application/json" \
  -d '{"name":"cyberark_ccp_rotation_state","content":[["asset","connector","safe","username","address","status","message","last_rotated","event_link","user_field","pwd_field"]]}'
```

### Step 7 — Set Asset Descriptions

For each target asset, set description to:
```
cyberark_ccp:safe=<Safe>,user_field=<username_field>,pwd_field=<password_field>[,address=<host>]
```

### Step 8 — Deploy

```bash
sudo su - phantom -c "phenv python3 /data/splunk/soar8/soar-playbooks/tools/deploy.py --env soar8 --source local --use-case credential_rotation 2>&1"
```

**Critical:** Always pass `--source local`. Without it, deploy.py checks `dist/soar6/*.tgz` first and uses stale GUI-exported tgz files if present.

Deploy order (handled automatically): CFs → cyberark_credential_rotation → cyberark_rotation_orchestrator → cyberark_recheck_handler

### Step 9 — Post-Deploy Configuration (SOAR UI)

| # | Playbook | Setting | Value | Notes |
|---|----------|---------|-------|-------|
| 1 | `cyberark_rotation_orchestrator` | Run as | `automation_cyberark_ccp` | Required for asset config writes |
| 2 | `cyberark_rotation_orchestrator` | Run automatically when | Container created | Prevent re-fire on artifact creation |
| 3 | `cyberark_rotation_orchestrator` | Active | Yes | |
| 4 | `cyberark_recheck_handler` | Run as | `automation_cyberark_ccp` | Required for asset config writes |
| 5 | `cyberark_recheck_handler` | Run automatically when | Artifact created | Must fire on "Recheck Request" artifact |
| 6 | `cyberark_recheck_handler` | Active | Yes | |

**After each deploy — deactivate previous versions:**
Each deploy creates new playbook IDs. Old versions remain active and will double-fire.
```bash
# Deactivate old orchestrator and recheck handler IDs from previous deploy
curl -sk -H "ph-auth-token: <TOKEN>" -X POST https://<HOST>/rest/playbook/<OLD_ID> \
  -H "Content-Type: application/json" -d '{"active":false,"cancel_runs":true}'
```

### Step 10 — Trigger E2E

```bash
curl -sk -H "ph-auth-token: <TOKEN>" -X POST https://soar6.karabox.cc:9443/rest/action_run \
  -H "Content-Type: application/json" \
  -d '{"action":"on poll","name":"manual_trigger","type":"poll","container_id":1,"targets":[{"assets":["cyberark_ccp"],"parameters":[{}],"app_id":149}]}'
```

Monitor:
```bash
# Latest container
curl -sk -H "ph-auth-token: <TOKEN>" "https://soar6.karabox.cc:9443/rest/container?sort=id&order=desc&page_size=1"
# Playbook runs on container
curl -sk -H "ph-auth-token: <TOKEN>" "https://soar6.karabox.cc:9443/rest/playbook_run?_filter_container=<ID>&sort=id&order=asc"
# State list
curl -sk -H "ph-auth-token: <TOKEN>" "https://soar6.karabox.cc:9443/rest/decided_list/cyberark_ccp_rotation_state"
```

---

## Verification Test Matrix

| # | Scenario | Setup | Expected | Validated |
|---|----------|-------|----------|-----------|
| 1 | Normal full rotation | f5_api_test description set, CyberArk mock reachable | status=success; state list updated | Pending (open issue #2) |
| 2 | Multi-target parallel | 4 target assets | 4 children dispatched simultaneously; all results collected | Partial ✓ (dispatch works; f5 fails issue #2) |
| 3 | Address disambiguation | splunk_primary + splunk_dr (same safe+username, different address) | Both rotated with correct passwords | Pending (open issue #3) |
| 4 | APPAP282E detection | app_server_test (mock count-based: 1st hit → APPAP282E) | status=pending_recheck; "Recheck Request" artifact created | ✓ (run 1408, container 755) |
| 5 | Recheck handler wakes | "Recheck Request" artifact with run_automation=True | cyberark_recheck_handler fires, waits 300s, retries | ✓ (validated in prior E2E, container 743) |
| 6 | Recheck success | Mock 2nd hit returns real password | status=success; "Recheck Succeeded" note | ✓ (container 743) |
| 7 | Recheck max attempts | 3 consecutive APPAP282E | "Recheck Failed - Max Attempts" note after attempt 3 | ✓ (container 743) |
| 8 | No configured assets | No `cyberark_ccp` description on any asset | Note: "No tagged assets found" | ✓ (container 743) |
| 9 | Tags preserved after rotation | After any rotation | `GET /rest/asset/{id}` → `tags` field unchanged | ✓ (container 743) |
| 10 | Orchestrator guard | "Recheck Request" artifact present in container | Orchestrator skips (no re-run of full rotation) | ✓ (container 743) |

---

## FR / NFR

| ID | Requirement | Implemented By |
|----|-------------|----------------|
| FR-1 | Timer-triggered scheduling | Timer app asset → label=cyberark_ccp → orchestrator |
| FR-2 | Auto-discovery of rotation targets | `asset_get_tagged_for_rotation` CF, description prefix `cyberark_ccp:` |
| FR-3 | Auto-discovery of CyberArk connector | `asset_list` CF with `asset_name` filter |
| FR-4 | Credential retrieval from CyberArk CCP | `phantom.act("get secret")` on CyberArk CCP asset |
| FR-5 | Asset configuration update (read-merge-write) | `asset_update_configuration` CF |
| FR-6 | Post-rotation connectivity test | `phantom.act("test connectivity")` on target asset |
| FR-7 | Multi-target parallel dispatch | `dispatch_rotations` loop + counter callback |
| FR-8 | Consolidated summary reporting | `add_summary_note` → `phantom.add_note()` |
| FR-9 | CyberArk failure — no stale credential write | CyberArk failure → `format_error` skips `update_target_asset` |
| FR-10 | Per-target result tracking | `phantom.save_playbook_output_data()` in `on_finish` |
| FR-11 | No-targets-found graceful handling | `add_no_targets_note` |
| FR-12 | Error propagation to summary | Error paths save to `format_result:output` run_data |
| FR-13 | Rotation state dashboard | `cyberark_ccp_rotation_state` custom list |
| FR-14 | APPAP282E → automatic recheck | `on_finish` creates "Recheck Request" artifact; `cyberark_recheck_handler` retries |
| FR-15 | Six distinct status values | `process_test_result` and `format_error` blocks |

| ID | Requirement | How Achieved |
|----|-------------|--------------|
| NFR-1 | Air-gapped deployability | Bundled `.whl` files; `.tgz` archives; `tools/deploy.py` |
| NFR-2 | SOAR 6.4.1 compatibility | `min_phantom_version: "6.4.1"`; Python 3.9 only |
| NFR-4 | Concurrency safety | No global state; `save_run_data`/`get_run_data` per container |
| NFR-5 | No credential leakage | `phantom.debug()` never logs passwords |
| NFR-6 | mTLS authentication | PEM cert/key → temp files per request, `requests.get(cert=(...))` |
| NFR-7 | Idempotent deployment | `force: True` on all REST import calls; `--source local` |
| NFR-8 | Observability | `phantom.debug()` at block entry; summary notes; spawn.log + actiond.log |
| NFR-11 | Graceful degradation | Individual child failures don't block others; collect_results handles per-child exceptions |
| NFR-13 | Least-privilege execution | `automation_cyberark_ccp` user; "Run As" set on both automation playbooks |

---

## Post-Build State (soar6.karabox.cc:9443 — 2026-04-17, v4.5 post-review)

| Component | SOAR ID | Version | Status |
|-----------|---------|---------|--------|
| `cyberark_rotation_orchestrator` | 764 | v43 | automation, label=cyberark_ccp, active |
| `credential_rotation` | 763 | v42 | data type — node 3 implicit tail |
| `cyberark_recheck_handler` | 765 | v43 | automation, label=cyberark_ccp, active |
| CF `cyberark_asset_update_configuration` | 580 | published | preserves tags + description on update |
| CF `cyberark_asset_get_tagged_for_rotation` | 581 | published | 10 outputs |

**E2E validation** (container 792, 2026-04-17): all 4 targets processed — f5_api_test → success; splunk_primary/dr → rotated (connectivity failed, expected); app_server_test → pending_recheck → recheck handler retry (300s) → rotated. Tags + descriptions preserved on all assets. Summary note, state list, recheck artifact + note all correct.

**Log locations:**
- `spawn.log`: action calls (`get secret`, `test connectivity`, `no op`)
- `decided.log`: code block debug entries
- `actiond.log`: connector action execution details
