"""
CyberArk Recheck Handler

Automation playbook (trigger: artifact_created, label=cyberark_ccp). Retries
cyberark_credential_rotation after an APPAP282E "Recheck Request" artifact,
bounded to 3 attempts. Architecture/flow detail: docs/usecases/uc1_dev_notes.md
"""


import phantom.rules as phantom
import json
import re
from datetime import datetime


def _recheck_run_name(target_asset, attempt):
    """Per-target, per-attempt dispatch name — NOT a shared literal.

    Previously every recheck dispatch used the fixed name "recheck_rotation"
    regardless of which target it was for, which made both artifact-claim
    checking and child-result lookup unable to distinguish between two
    different targets' concurrent recheck attempts. Sanitized since asset
    names flow into a playbook_run name field.
    """
    safe_target = re.sub(r"[^A-Za-z0-9_]", "_", str(target_asset or "unknown"))
    return "recheck_{}_{}".format(safe_target, attempt)


def _recheck_already_dispatched(container, target_asset, attempt):
    """REST idempotency check — has this target/attempt's recheck already been
    dispatched by this or a concurrently-running execution? Same pattern as
    cyberark_rotation_orchestrator's collect_results (REST-based, not local
    run_data, since run_data isn't shared across separate automation-triggered
    executions)."""
    run_name = _recheck_run_name(target_asset, attempt)
    try:
        container_id = container.get("id")
        url = phantom.build_phantom_rest_url("playbook_run")
        resp = phantom.session_get(
            url,
            params={"_filter_container": container_id, "page_size": 0},
            verify=False,
        )
        if resp.status_code != 200:
            phantom.error("session_get playbook_run returned status {}".format(resp.status_code))
            return False
        for run in resp.json().get("data", []):
            misc = run.get("misc") or {}
            parent_info = misc.get("parent_playbook_run") or {}
            if parent_info.get("child_playbook_run_name") == run_name:
                return True
        return False
    except Exception as e:
        phantom.error("Failed to check for existing recheck dispatch: {}".format(e))
        return False


@phantom.playbook_block()
def on_start(container):
    phantom.debug('on_start() called')

    check_recheck_artifact(container=container)

    return


@phantom.playbook_block()
def check_recheck_artifact(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("check_recheck_artifact() called")

    check_recheck_artifact__target = None

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Code: artifact iteration to find latest "Recheck Request" + max-attempts guard. No native block
    # iterates container artifacts and applies a bounded-retry guard in one step.
    MAX_RECHECK_ATTEMPTS = 3
    RECHECK_DELAY_SECONDS = 300

    artifacts = phantom.collect2(
        container=container,
        datapath=[
            "artifact:*.name",
            "artifact:*.cef.cs1",
            "artifact:*.cef.cn1",
            "artifact:*.cef.cs2",
            "artifact:*.id",
        ]
    )

    # Highest-id-first, skip-if-already-dispatched — see uc1_dev_notes.md
    candidates = []
    for row in artifacts:
        name, target_asset, attempt, params_json, art_id = row
        if name == "Recheck Request":
            candidates.append({
                "target_asset": target_asset,
                "attempt": int(attempt or 1),
                "params_json": params_json,
                "id": art_id or 0,
            })
    candidates.sort(key=lambda c: c["id"], reverse=True)

    recheck = None
    for candidate in candidates:
        if _recheck_already_dispatched(container, candidate["target_asset"], candidate["attempt"]):
            phantom.debug("Recheck for '{}' attempt {} already dispatched — checking next candidate".format(
                candidate["target_asset"], candidate["attempt"]))
            continue
        recheck = candidate
        break

    if not recheck:
        phantom.debug("No unclaimed Recheck Request artifacts found — skipping")
        return

    target_asset = recheck["target_asset"]
    attempt = recheck["attempt"]

    if attempt > MAX_RECHECK_ATTEMPTS:
        phantom.debug("Max recheck attempts ({}) exceeded for '{}' — stopping".format(
            MAX_RECHECK_ATTEMPTS, target_asset))

        phantom.add_note(
            container=container,
            note_type="general",
            title="Recheck Failed - Max Attempts",
            content="Credential recheck for '{}' stopped after {} attempts. "
                    "CyberArk password change may still be in progress. "
                    "Manual intervention required.".format(target_asset, MAX_RECHECK_ATTEMPTS),
        )
        return

    check_recheck_artifact__target = recheck

    phantom.debug("Waiting {}s before recheck attempt {}/{} for '{}'".format(
        RECHECK_DELAY_SECONDS, attempt, MAX_RECHECK_ATTEMPTS, target_asset))

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.save_run_data(key="check_recheck_artifact:target", value=json.dumps(check_recheck_artifact__target))

    wait_before_recheck(container=container)

    return


@phantom.playbook_block()
def wait_before_recheck(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("wait_before_recheck() called")

    RECHECK_DELAY_SECONDS = 300
    parameters = [{"sleep_seconds": RECHECK_DELAY_SECONDS}]

    phantom.act("no op", parameters=parameters, name="wait_before_recheck", assets=["soar6"], callback=dispatch_recheck)

    return


@phantom.playbook_block()
def dispatch_recheck(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("dispatch_recheck() called")

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Code, not playbook block: inputs come from run_data (check_recheck_artifact:target).
    # A native playbook block would require the input to be a standard datapath, not a JSON blob.
    recheck = {}
    try:
        recheck = json.loads(phantom.get_run_data(key="check_recheck_artifact:target") or "{}")
    except Exception:
        pass

    target_asset = recheck.get("target_asset", "unknown")
    attempt = recheck.get("attempt", 1)

    # Parse rotation params and dispatch cyberark_credential_rotation
    try:
        params = json.loads(recheck.get("params_json", "{}"))
    except Exception:
        params = {}

    inputs = {
        "target_asset": target_asset,
        "safe": params.get("safe", ""),
        "username": params.get("username", ""),
        "pwd_field": params.get("pwd_field", "password"),
        "user_field": params.get("user_field", "username"),
    }
    if params.get("address"):
        inputs["address"] = params["address"]

    phantom.debug("Dispatching cyberark_credential_rotation for '{}' (attempt {})".format(
        target_asset, attempt))

    phantom.playbook(
        playbook="local/cyberark_credential_rotation",
        container=container,
        name=_recheck_run_name(target_asset, attempt),
        inputs=inputs,
        callback=process_recheck_result,
    )

    ################################################################################
    ## Custom Code End
    ################################################################################

    return


@phantom.playbook_block()
def process_recheck_result(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("process_recheck_result() called")

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Sync-only multi-mutation post-callback — see uc1_dev_notes.md
    if results is None:
        return

    MAX_RECHECK_ATTEMPTS = 3
    STATE_LIST_NAME = "cyberark_ccp_rotation_state"

    recheck = {}
    try:
        recheck = json.loads(phantom.get_run_data(key="check_recheck_artifact:target") or "{}")
    except Exception:
        pass

    target_asset = recheck.get("target_asset", "unknown")
    attempt = int(recheck.get("attempt", 1))
    expected_run_name = _recheck_run_name(target_asset, attempt)

    # Read child PB output via REST, filtered to this execution's own run name
    result = None
    try:
        container_id = container.get("id")
        url = phantom.build_phantom_rest_url("playbook_run")
        resp = phantom.session_get(
            url,
            params={
                "_filter_container": container_id,
                "sort": "id",
                "order": "desc",
                "page_size": 10,
            },
            verify=False,
        )
        if resp.status_code == 200:
            resp_json = resp.json()
            for run in resp_json.get("data", []):
                misc = run.get("misc") or {}
                parent_info = misc.get("parent_playbook_run") or {}
                run_name = parent_info.get("child_playbook_run_name", "")
                if run_name == expected_run_name:
                    outputs = run.get("outputs") or []
                    if outputs:
                        first_out = outputs[0]
                        result = json.loads(first_out) if isinstance(first_out, str) else first_out
                    break
    except Exception as e:
        phantom.error("Failed to read recheck child output: {}".format(e))

    if not result:
        result = {"status": "unknown", "message": "No result from cyberark_credential_rotation"}

    status = result.get("status", "unknown")
    phantom.debug("Recheck result for '{}': status={}".format(target_asset, status))

    # Update state list
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    event_id = str(container.get("id", ""))
    soar_base = phantom.get_base_url() or ""
    event_link = "{}/mission/{}".format(soar_base, event_id)

    try:
        state = {}
        read_success, _msg, rows = phantom.get_list(list_name=STATE_LIST_NAME)
        if read_success and rows:
            for row in rows:
                if row and len(row) >= 11 and row[0] != "asset":
                    state[row[0]] = row

        params = {}
        try:
            params = json.loads(recheck.get("params_json", "{}"))
        except Exception:
            pass

        # Column order matches update_rotation_state — see uc1_dev_notes.md
        existing = state.get(target_asset, [""] * 11)
        state[target_asset] = [
            target_asset,
            params.get("safe", ""),
            params.get("user_field", existing[2] if target_asset in state else "username"),
            params.get("pwd_field", existing[3] if target_asset in state else "password"),
            params.get("address", ""),
            existing[5] if target_asset in state else "",
            params.get("username", ""),
            status,
            (result.get("message", ""))[:200],
            now_str,
            event_link,
        ]

        header = [
            "asset", "safe", "user_field", "pwd_field", "address",
            "connector", "username", "status", "message", "last_rotated", "event_link",
        ]
        content = [header] + [state[k] for k in sorted(state)]
        phantom.set_list(list_name=STATE_LIST_NAME, values=content)
        phantom.debug("State list updated for '{}'".format(target_asset))
    except Exception as e:
        phantom.error("Failed to update state list: {}".format(e))

    # Decide next action based on result
    if status == "success" or status.startswith("rotated"):
        phantom.debug("Recheck succeeded for '{}'".format(target_asset))
        phantom.add_note(
            container=container,
            note_type="general",
            title="Recheck Succeeded - {}".format(target_asset),
            content="Credential recheck for '{}' succeeded on attempt {}.\n\n{}".format(
                target_asset, attempt, result.get("message", "")),
        )

    elif result.get("password_change_in_process") or status in ("pending_recheck", "rotated (change pending)"):
        next_attempt = attempt + 1
        if next_attempt > MAX_RECHECK_ATTEMPTS:
            phantom.debug("Max attempts reached for '{}' after attempt {}".format(
                target_asset, attempt))
            phantom.add_note(
                container=container,
                note_type="general",
                title="Recheck Failed - Max Attempts",
                content="Credential recheck for '{}' still pending after {} attempts. "
                        "CyberArk password change may still be in progress. "
                        "Manual intervention required.\n\n{}".format(
                            target_asset, MAX_RECHECK_ATTEMPTS, result.get("message", "")),
            )
        else:
            phantom.debug("Creating retry artifact for '{}' (attempt {})".format(
                target_asset, next_attempt))

            cef_data = {
                "message": "Recheck request for {} (attempt {})".format(target_asset, next_attempt),
                "cs1": target_asset,
                "cs1Label": "target_asset",
                "cn1": next_attempt,
                "cn1Label": "attempt",
                "cs2": recheck.get("params_json", "{}"),
                "cs2Label": "rotation_params",
            }

            success_flag, msg, art_id = phantom.add_artifact(
                container=container,
                raw_data={},
                cef_data=cef_data,
                label="events",
                name="Recheck Request",
                severity="low",
                identifier=None,
                artifact_type="network",
                run_automation=True,
            )
            phantom.debug("Retry artifact created: success={}, id={}, attempt={}".format(
                success_flag, art_id, next_attempt))

    else:
        phantom.debug("Recheck failed for '{}': {}".format(target_asset, status))
        phantom.add_note(
            container=container,
            note_type="general",
            title="Recheck Failed - {}".format(target_asset),
            content="Credential recheck for '{}' failed on attempt {}.\n\nStatus: {}\n{}".format(
                target_asset, attempt, status, result.get("message", "")),
        )

    # Re-evaluate container severity based on all asset statuses in state list
    try:
        all_statuses = []
        read_ok, _, all_rows = phantom.get_list(list_name=STATE_LIST_NAME)
        if read_ok and all_rows:
            for row in all_rows:
                if row and len(row) >= 11 and row[0] != "asset":
                    all_statuses.append(row[7])  # status column — see header order above

        if all_statuses:
            if all(s == "success" for s in all_statuses):
                new_sev = "low"
            elif any(s == "failed" for s in all_statuses):
                new_sev = "high"
            elif any(s in ("pending_recheck", "rotated (change pending)") for s in all_statuses):
                new_sev = "medium"
            else:
                new_sev = "medium"
        else:
            new_sev = "low"

        phantom.set_severity(container=container, severity=new_sev)
        phantom.debug("Container severity updated to '{}'".format(new_sev))
    except Exception as e:
        phantom.error("Failed to update container severity: {}".format(e))

    ################################################################################
    ## Custom Code End
    ################################################################################

    return


def on_finish(container, summary):
    phantom.debug("on_finish() called")
    return
