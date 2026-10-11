# Automated Credential Rotation (UC1) — Implementation Plan

Current design. How it got here (releases, migrations, investigations): `uc1_history.md`, not shipped
in the handover. Open work: the Splunk project's `docs/next-steps.md` (not shipped).

## Scope

- SOAR assets (F5, Splunk, app servers…) hold credentials that CyberArk rotates in its vault. On a
  timer, UC1 fetches each target asset's current password from CyberArk CCP (AppID + mTLS), writes it
  into the asset's configuration and tests the asset's connectivity.
- When CyberArk reports a password change in progress (APPAP282E), the target is retried 5 minutes
  later, at most 3 times.
- The targets and their last result live in one custom list, `cyberark_ccp_rotation_state`.
- Out of scope: rotation history (the list keeps the latest result only), notifications beyond the
  container note.

## Architecture

| Component | Type | Trigger / label | Role |
|---|---|---|---|
| `cyberark_rotation_orchestrator` | automation, active | `cyberark_ccp` | Reads the targets, starts one rotation per target, writes the summary note, the list and the severity |
| `cyberark_credential_rotation` | data | — (run by the other two) | Rotates one target |
| `cyberark_recheck_handler` | automation, active | `cyberark_ccp` | Retries a target after a `Recheck Request` artifact |
| CF `cyberark_asset_get_tagged_for_rotation` | custom function | orchestrator | Reads the targets from the list |
| CF `cyberark_asset_update_configuration` | custom function | rotation | Read-merge-write of one asset's configuration |

```
Timer asset cyberark_ccp (label cyberark_ccp, every 24 h) → new container
  → orchestrator: discover_targets (CF) → read_discover_result → check_targets
       no target → format_no_targets_note → add_note_no_targets (asset soar8)
       targets   → dispatch_rotations: phantom.playbook(cyberark_credential_rotation) per target
                 → collect_results → build_summary → add_summary_note
                 → update_rotation_state → update_severity
  → rotation (per target): validate_inputs → get_secret_from_vault (asset cyberark ccp mock)
       → build_config_update → update_decision
            ready → update_target_asset (CF) → run_test_connectivity
            error → format_error
       on_finish: playbook output; APPAP282E → Recheck Request artifact (run_automation)
  → recheck handler (on that artifact): check_recheck_artifact → wait_before_recheck
       (no op 300 s, asset soar8) → dispatch_recheck → process_recheck_result
```

**Rules the code follows:**

- Both automation playbooks trigger on `artifact_created`: the Timer's container arrives with an
  artifact (a container created without one triggers nothing), and every later artifact of the label
  starts both again. The orchestrator runs once per container and skips a container that holds a
  `Recheck Request`; the recheck handler skips one that holds none.
- After a `phantom.playbook()` callback, only synchronous platform APIs are used
  (`phantom.add_note`, `get_list`/`set_list`, `set_severity`, `add_artifact`, REST reads): an
  asynchronous `phantom.act` or custom function would race `on_finish`. That is why the summary,
  list and severity are code blocks, not a CF or an action.
- The VPE has no for-each and no "join N children" block: `dispatch_rotations` starts one child per
  target, and `collect_results` counts finished children over REST (paginated, idempotent) instead
  of a run-data counter.
- A CyberArk failure never writes a credential: `format_error` skips the asset update.

## Playbooks

### `cyberark_rotation_orchestrator`

No inputs or outputs. `discover_targets` calls the discovery CF; `read_discover_result` exists only
because a utility block edged straight into a decision misrenders in the VPE. No target → the note
`Credential Rotation - No Targets` (written through the `soar8` asset). Otherwise each child gets
`target_asset`, `safe`, `username`, `pwd_field`, `user_field`, `address`; when all have finished,
`build_summary` writes `Credential Rotation - <date time>` (one row per target) and sets the
container severity: all success → low, any failed → high, any pending → medium. A discovery failure
with nothing rotated counts as failed. `collect_results`' "summary done" guard is check-then-act, so
`add_summary_note` also checks for an existing summary note before writing.

### `cyberark_credential_rotation`

Inputs: `target_asset`, `safe`, `username`, `pwd_field`, `user_field`, `address` (optional).
Output: `status`.

- `validate_inputs` (native decision): `safe` and `username` must be set, else `format_error`.
- `get_secret_from_vault` (`get secret`; `address` is sent only when set).
- `build_config_update` parses the reply: APPAP282E / `password_change_in_process` → error path;
  else the config update keyed by `pwd_field`.
- `update_target_asset` (CF) writes it; `run_test_connectivity` checks the CF result, then runs
  `test connectivity` on the target asset over REST (`POST /rest/action_run` + poll): a native action
  block needs an asset chosen at design time, this one is chosen at run time.
- `on_finish` saves the output and, for APPAP282E, adds a `Recheck Request` artifact with
  `run_automation` on: `cs1` target asset, `cn1` attempt (1), `cs2` the rotation parameters (JSON).

Statuses: `success` (rotated, connectivity passed), `rotated (connectivity failed)`, `rotated (no test
result)` (the target's app has no working `test connectivity`), `rotated (change pending)`,
`pending_recheck` (APPAP282E), `failed`.

### `cyberark_recheck_handler`

`check_recheck_artifact` takes the newest `Recheck Request` that has not been dispatched yet (several
targets can have one in the same container; the dispatch name is per target and attempt) and stops
after attempt 3 with `Recheck Failed - Max Attempts`. `wait_before_recheck` is a `no op` of 300 s on
the `soar8` asset. `process_recheck_result` reads the child's output over REST, updates the list,
writes `Recheck Succeeded - <asset>` or `Recheck Failed - <asset>`, adds the next `Recheck Request`
(attempt + 1) while CyberArk still answers APPAP282E, and re-evaluates the container severity from
the whole list.

### Custom functions

- `cyberark_asset_get_tagged_for_rotation` (input `list_name`, default the state list): for each row,
  looks the asset up by name (skips a row whose asset no longer exists), reads the username from the
  asset's `user_field`, and resolves the app name over `GET /rest/app/{id}` (an asset's `app_name` is
  empty in automation context). Outputs: `asset_name`, `asset_id`, `safe`, `username`, `user_field`,
  `pwd_field`, `address`, `app_name`, `total_count`.
- `cyberark_asset_update_configuration` (inputs `asset`, `configuration_updates` JSON): `GET
  /rest/asset/{id}`, merge, `POST` the full record (name, tags, description, configuration — an omitted
  field is reset). Outputs: `success`, `asset_id`, `asset_name`, `updated_fields`, `message`.

## Data model

**`cyberark_ccp_rotation_state`** — columns 1-5 are the targets (input), 6-11 the last result (output):

| # | Column | Written by |
|---|---|---|
| 1-5 | `asset`, `safe`, `user_field`, `pwd_field`, `address` (optional) | the operator |
| 6-7 | `connector`, `username` | the orchestrator, from discovery |
| 8-11 | `status`, `message`, `last_rotated`, `event_link` | the orchestrator and the recheck handler |

`user_field` / `pwd_field` are the target asset's configuration keys that hold the username and the
password. `address` tells apart CyberArk accounts with the same username in one safe.

**Connector `cyberark_ccp`:** `get secret` (`safe`, `username`, optional `object`, `address`) against
CCP's `/AIMWebService/api/Accounts` with the asset's AppID, over mTLS (PEM cert/key written to temp files per call).
APPAP282E means the password is being changed in the vault.

## Setup Guide

1. **Label** `cyberark_ccp` (Administration → Event Settings → Labels).
2. **Automation user** for the two automation playbooks, role **Admin**: the asset write runs through
   REST as that user, and a weaker role makes every rotation fail with HTTP 403.
3. **Apps:** CyberArk CCP (this package's connector), Timer, and the SOAR (Phantom) app; each target
   asset's own app needs a working `test connectivity`, or its status is `rotated (no test result)`.
4. **Assets** (the playbooks ship pointed at these names; keep them, or re-point the blocks in the VPE
   and save):

   | Asset | App | Settings | Used by |
   |---|---|---|---|
   | `cyberark ccp mock` | CyberArk CCP | `base_url`, `app_id`, `client_cert`/`client_key` (PEM), `client_ca`, `verify_ssl`, `timeout`, `test_safe`/`test_username` (the account Test Connectivity reads); Test Connectivity before going on | `get_secret_from_vault` |
   | `cyberark_ccp` | Timer | label `cyberark_ccp`, interval 1440 min | trigger |
   | `soar8` | SOAR (Phantom) | the SOAR instance itself | `add_note_no_targets`, `wait_before_recheck` |

   Enter every credential by hand: password fields do not cross the air gap as usable values.
5. **Custom list** `cyberark_ccp_rotation_state` with the header row `asset, safe, user_field,
   pwd_field, address, connector, username, status, message, last_rotated, event_link`, then one row
   per target with columns 1-5 filled.
6. **Import** the two CFs (and publish them), then the three playbooks.
7. **Activate** `cyberark_rotation_orchestrator` and `cyberark_recheck_handler`, **Run As** the
   automation user; leave `cyberark_credential_rotation` inactive. After any redeploy, read the active
   flags back.

## Verification

- **No target:** a new `cyberark_ccp` container with one artifact (as the Timer creates it) and no
  target row → one orchestrator run and the note `Credential Rotation - No Targets`.
- **Rotation:** one row for a test asset → `success` in the list and the summary note; the asset's
  tags and description unchanged; severity low.
- **APPAP282E:** a target whose CyberArk answer is APPAP282E (the lab mock answers it on the first
  call for its test account) → `pending_recheck`, a `Recheck Request` artifact, a retry after 300 s,
  then `Recheck Succeeded`; three APPAP282E in a row → `Recheck Failed - Max Attempts`.
- **Logs** on the SOAR host (as `phantom`): `spawn.log`, `decided.log`, `actiond.log`.

## Known limitations

- `cyberark_asset_update_configuration` writes every configuration field back, password fields
  included; a password field read over REST comes back encrypted, so any password field other than
  the one rotated can be corrupted. The CyberArk asset's own `client_key` was corrupted twice that
  way. Not fixed.
- `collect_results`' guard is not atomic (accepted residual race, memory
  `project_uc1_deferred_finding_4.md`), and it has no timeout; the recheck handler wakes on every
  artifact of the label.
- `cyberark_credential_rotation`'s `format_error` is reached from two alternative paths; a VPE save
  turns that into a join. `run_test_connectivity` polls with `sleep` (lint W0001).
- The list keeps the latest result per asset only.
