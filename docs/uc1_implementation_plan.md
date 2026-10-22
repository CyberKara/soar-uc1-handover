# Automated Credential Refresh (UC1) — Implementation Plan

Current design (since 2026-10-22). How it got here: `uc1_rework_plan.md` (the push-vs-pull challenge
and the decisions) and `uc1_history.md`; neither is shipped in the handover. Open work: the Splunk
project's `docs/next-steps.md` (not shipped).

## Scope

- SOAR assets (F5, Splunk, app servers…) hold credentials that CyberArk changes in its vault. On a
  timer, UC1 reads each target's current password from CyberArk CCP (AppID + mTLS), writes it into the
  asset's password field and, optionally, tests the asset's connectivity.
- The targets and their last result live in one custom list, `cyberark_ccp_rotation_state`.
- SOAR's built-in password vault would fetch passwords at use instead; it has no CCP provider, so it
  does not fit a CCP-only CyberArk (rework plan, section 3).
- Out of scope: rotation history (the list keeps the latest result only), notifications beyond the
  container note.

## Architecture

One automation playbook, `cyberark_credential_refresh` (label `cyberark_ccp`, trigger
`artifact_created`, active), and five custom functions `cyberark_ccp_*`. Native blocks only: utility
(the custom functions), filter, action. No child playbook, no recheck handler, no code block.

```
Timer asset cyberark_ccp (every 24 h) → container + one artifact
  → read_targets (cyberark_ccp_get_targets)          targets + the CyberArk accounts to query
  → filter anything_to_query
       no  → report_nothing_queried (cyberark_ccp_report)
       yes → get_secrets: get secret, one result per account (asset cyberark ccp mock)
           → classify_secrets (cyberark_ccp_classify_secrets)   write | pending (APPAP282E) | failed
           → filter anything_to_write
                no  → report_nothing_written (cyberark_ccp_report)
                yes → write_passwords (cyberark_ccp_update_asset)   {pwd_field: password} per asset
                    → start_tests (cyberark_ccp_start_tests)         REST test connectivity per asset
                    → wait_for_tests: no op (asset soar8)
                    → report (cyberark_ccp_report)                    list, one note, severity
```

The targets travel from one function to the next as `targets_json` (asset, safe, username,
fields, status, message — never a password).

**Rules the design follows:**

- A password never passes through a block output: `classify_secrets` gets statuses and messages
  only, and `write_passwords`' Custom Code reads the password from `get_secrets`' result.
- A write sends only the password field. SOAR keeps every configuration key a POST leaves out, and a
  read-back password field is `********`: posting it back would store that.
- Each "nothing to do" branch has its own report block (same function), so no block has two incoming
  paths. The filters compare a `yes`/`no` output, not a number.
- The test runs over REST (`POST /rest/action_run`) inside a custom function: a native action block
  runs on an asset chosen in the editor, this one is chosen at run time. The wait is a native `no op`.
- Custom Code is left in two blocks only: `get_secrets` unzips the three bound lists into one
  parameter set per account, `write_passwords` adds each password. A VPE save keeps both.
- A second run on the same container (an artifact added later, a manual run) refreshes again; that is
  harmless, so there is no re-entry guard.

## Playbook `cyberark_credential_refresh`

Settings are input values on the `start_tests` block, edited on the canvas: `test_connectivity`
(`true`; `false` = write only, status `written`) and `wait_seconds` (60; the wait is 1 second when no
test started).

| Status | Meaning | Severity |
|---|---|---|
| `success` | Written; test connectivity passed | low |
| `written` | Written; test connectivity switched off | low |
| `written (test failed)` | Written; the test failed (the connector's reason in the message) | high |
| `written (no test result)` | Written; the test did not start or was still running after the wait | medium |
| `written (change pending)` | CCP returned the password with `PasswordChangeInProcess`; the next run writes the new one | medium |
| `pending` | APPAP282E: nothing written, the next run retries | medium |
| `failed` | CyberArk error, row unusable (asset missing, username field empty…) or write refused | high |

The container gets the highest severity of its rows. The note `Credential Refresh - <date time>`
holds one table row per target (split in parts over 19,000 characters).

## Custom functions

| Function | Inputs | Does |
|---|---|---|
| `cyberark_ccp_get_targets` | `list_name` | One target per list row with the asset's id, app id and app name (`?pretty`: the Automation role cannot read apps) and the username from its `user_field`; an unusable row is `failed`. Outputs `targets_json`, `has_queries`, and the accounts to query as parallel lists `safes`, `usernames`, `addresses` (one per account) |
| `cyberark_ccp_classify_secrets` | `targets_json`; lists of `get secret` parameter safe/username/address, status, message, `password_change_in_process` | Marks each target write, `pending` or `failed`. Outputs `targets_json`, `has_writes`, `write_assets`, `write_fields` |
| `cyberark_ccp_update_asset` | `asset`, `configuration_updates` (JSON) | Posts only the given keys plus the asset's name, tags and description; echoes `asset_name` on failure too |
| `cyberark_ccp_start_tests` | `targets_json`; lists of update results; `test_connectivity`, `wait_seconds`, `container_id` | Starts test connectivity per written asset over REST. Outputs `targets_json`, `test_count`, `wait_seconds` |
| `cyberark_ccp_report` | `targets_json`, `container_id`, `list_name` | Reads the test results (the reason from the app run), writes columns 6-11 of the list, one note, the container severity (REST) |

## Data model

**`cyberark_ccp_rotation_state`** — columns 1-5 are the targets (input), 6-11 the last result (output):

| # | Column | Written by |
|---|---|---|
| 1-5 | `asset`, `safe`, `user_field`, `pwd_field`, `address` (optional) | the operator |
| 6-7 | `connector`, `username` | the playbook, from the asset |
| 8-11 | `status`, `message`, `last_rotated`, `event_link` | the playbook |

`user_field` / `pwd_field` are the target asset's configuration keys for the username and the
password. `address` tells apart CyberArk accounts with the same username in one safe. The playbook
rewrites columns 6-11 and keeps the operator's rows and their order.

## Setup Guide

1. **Label** `cyberark_ccp` (Administration → Event Settings → Labels). Restrict who can see it: the
   `get secret` results on its containers hold the passwords (Known limitations).
2. **Role** `cyberark_credential_refresh`: a copy of the built-in Automation role with **Assets: Edit**
   allowed. **Automation user** (e.g. `cyberark_refresh`) with that role. Without asset edit every
   write reads `User "…" is not authorized to edit assets`. Administrator is not needed.
3. **Apps:** CyberArk CCP (this package's connector), Timer, and the SOAR (Phantom) app; each target
   asset's own app needs a working `test connectivity`, or its status is `written (no test result)`.
4. **Assets** (the playbook ships pointed at these names; keep them, or re-point the blocks in the VPE
   and save):

   | Asset | App | Settings | Used by |
   |---|---|---|---|
   | `cyberark ccp mock` | CyberArk CCP | `base_url`, `app_id`, `client_cert`/`client_key` (PEM), `client_ca`, `verify_ssl`, `timeout`, `test_safe`/`test_username`; Test Connectivity before going on | `get_secrets` |
   | `cyberark_ccp` | Timer | label `cyberark_ccp`, interval 1440 min (shorter = smaller stale window) | trigger |
   | `soar8` | SOAR (Phantom) | the SOAR instance itself | `wait_for_tests` |

   Enter every credential by hand: password fields do not cross the air gap as usable values.
5. **Custom list** `cyberark_ccp_rotation_state` with the header row `asset, safe, user_field,
   pwd_field, address, connector, username, status, message, last_rotated, event_link`, then one row
   per target with columns 1-5 filled.
6. **Import** the five `cyberark_ccp_*` custom functions (and publish them), then the playbook.
7. **In the VPE:** Playbook Settings → **Run As** the automation user of step 2, save, then
   **activate** it. Run As is not carried by an import; check it after every re-import.

## Verification

Lab, soar8, 2026-10-22 (code-block version: containers 5938, 5940-5946; this version: 5951-5955):

| Case | Result |
|---|---|
| Target in the list, right password in CyberArk | `success`: written, test connectivity passed |
| Wrong password in CyberArk | `written (test failed)` with the connector's reason: the write happened |
| APPAP282E (first request for a changing account) | `pending`, nothing written |
| Unknown safe / asset missing from SOAR | `failed`, with CyberArk's message / `Asset not found` |
| Automation user without asset edit | `failed`: `User "automation" is not authorized to edit assets` |
| `test_connectivity` false | `written`, no test, a 1-second wait |
| Nothing to write (only pending / failed) | `report_nothing_written`: one note |
| Empty list | `report_nothing_queried`: one note `No target`, severity low |
| Run As `cyberark_refresh` (Automation + asset edit), `automation` without it | `success` (playbook 742, container 5974) |

Not reproduced in the lab: `written (change pending)` (the mock answers APPAP282E whenever the flag
is set, as CCP does with `FailRequestOnPasswordChange`) and `written (no test result)`.

On the appliance: one row for a test asset → `success` in the list and the note.

## Known limitations

- The password is visible to anyone who can open the `cyberark_ccp` containers: in the `get secret`
  action result and in the `write_passwords` (`cyberark_ccp_update_asset`) run's parameters. Restrict
  the label.
- After CyberArk changes a password, the asset keeps the old one until the next run (up to the Timer
  interval); `pending` and `written (change pending)` also wait for the next run.
- Run As is set by hand in the VPE.
- The list keeps the latest result per asset only.
