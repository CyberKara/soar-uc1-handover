"""
CyberArk Rotation Orchestrator

Automation playbook (trigger: artifact_created, label=cyberark_ccp). Discovers
tagged assets, dispatches cyberark_credential_rotation per target, collects
results, updates the state list. Architecture/flow detail: docs/uc1_dev_notes.md
"""


import phantom.rules as phantom
import json
from datetime import datetime


@phantom.playbook_block()
def on_start(container):
    phantom.debug('on_start() called')

    # Guard: only run once per container
    existing = phantom.collect2(container=container, datapath=["artifact:*.name"])
    for row in existing:
        if row[0] == "Recheck Request":
            phantom.debug("Triggered by Recheck Request artifact — skipping orchestration")
            return

    discover_targets(container=container)

    return


@phantom.playbook_block()
def discover_targets(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("discover_targets() called")

    parameters = [{"list_name": "cyberark_ccp_rotation_state"}]

    phantom.custom_function(custom_function="local/cyberark_asset_get_tagged_for_rotation", parameters=parameters, name="discover_targets", callback=read_discover_result)

    return


@phantom.playbook_block()
def read_discover_result(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("read_discover_result() called")

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Bridge block working around a VPE rendering bug
    target_result = phantom.collect2(
        container=container,
        datapath=["discover_targets:custom_function_result.data.total_count"]
    )
    total = target_result[0][0] if target_result else 0
    phantom.debug("Discovered {} rotation targets".format(total))

    ################################################################################
    ## Custom Code End
    ################################################################################

    check_targets(container=container)

    return


@phantom.playbook_block()
def check_targets(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("check_targets() called")

    found_match_1 = phantom.decision(
        container=container,
        conditions=[
            ["discover_targets:custom_function_result.data.total_count", ">", 0]
        ])

    if found_match_1:
        dispatch_rotations(action=action, success=success, container=container, results=results, handle=handle)
        return

    format_no_targets_note(action=action, success=success, container=container, results=results, handle=handle)

    return


@phantom.playbook_block()
def dispatch_rotations(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("dispatch_rotations() called")

    dispatch_rotations__total = None
    dispatch_rotations__error = None
    dispatch_rotations__targets = None

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Dynamic N-target fan-out
    targets_info = []

    target_data = phantom.collect2(
        container=container,
        datapath=[
            "discover_targets:custom_function_result.data.asset_name",
            "discover_targets:custom_function_result.data.safe",
            "discover_targets:custom_function_result.data.username",
            "discover_targets:custom_function_result.data.user_field",
            "discover_targets:custom_function_result.data.pwd_field",
            "discover_targets:custom_function_result.data.address",
            "discover_targets:custom_function_result.data.app_name",
        ]
    )

    if not target_data:
        dispatch_rotations__error = "No target data from discover_targets"
        phantom.error(dispatch_rotations__error)
        dispatch_rotations__total = 0
        dispatch_rotations__targets = []
        phantom.save_run_data(key="dispatch_rotations:total", value=json.dumps(dispatch_rotations__total))
        phantom.save_run_data(key="dispatch_rotations:error", value=json.dumps(dispatch_rotations__error))
        phantom.save_run_data(key="dispatch_rotations:targets", value=json.dumps(dispatch_rotations__targets))
        build_summary(container=container)
        return

    for row in target_data:
        targets_info.append({
            "asset": row[0], "safe": row[1], "username": row[2],
            "user_field": row[3], "pwd_field": row[4],
            "address": row[5] or "", "connector": row[6] or "",
        })

    if not targets_info:
        dispatch_rotations__error = "No targets to process"
        phantom.error(dispatch_rotations__error)
        dispatch_rotations__total = 0
        dispatch_rotations__targets = []
        phantom.save_run_data(key="dispatch_rotations:total", value=json.dumps(dispatch_rotations__total))
        phantom.save_run_data(key="dispatch_rotations:error", value=json.dumps(dispatch_rotations__error))
        phantom.save_run_data(key="dispatch_rotations:targets", value=json.dumps(dispatch_rotations__targets))
        build_summary(container=container)
        return

    total = len(targets_info)
    dispatch_rotations__total = total
    dispatch_rotations__error = None
    dispatch_rotations__targets = targets_info
    phantom.save_run_data(key="dispatch_rotations:total", value=json.dumps(dispatch_rotations__total))
    phantom.save_run_data(key="dispatch_rotations:error", value=json.dumps(dispatch_rotations__error))
    phantom.save_run_data(key="dispatch_rotations:targets", value=json.dumps(dispatch_rotations__targets))

    for idx, t in enumerate(targets_info):
        phantom.debug("Dispatching rotation {}/{}: asset='{}', safe='{}', user='{}'".format(
            idx + 1, total, t["asset"], t["safe"], t["username"]))

        inputs = {
            "target_asset": t["asset"],
            "safe": t["safe"],
            "username": t["username"],
            "pwd_field": t["pwd_field"],
            "user_field": t["user_field"],
        }
        if t.get("address"):
            inputs["address"] = t["address"]

        phantom.playbook(
            playbook="local/cyberark_credential_rotation",
            container=container,
            name="rotation_{}".format(idx),
            inputs=inputs,
            callback=collect_results
        )

    ################################################################################
    ## Custom Code End
    ################################################################################

    return


@phantom.playbook_block()
def collect_results(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("collect_results() called")

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # REST-based child output aggregation
    if results is None:
        return

    total = int(phantom.get_run_data(key="dispatch_rotations:total") or "0")

    # Idempotent + paginated REST count
    child_runs_by_name = {}
    PAGE_SIZE = 50
    MAX_PAGES = 20  # safety bound: 1000 rows, far beyond any realistic container
    try:
        container_id = container.get("id")
        url = phantom.build_phantom_rest_url("playbook_run")
        for page in range(MAX_PAGES):
            resp = phantom.session_get(
                url,
                params={
                    "_filter_container": container_id,
                    "sort": "id",
                    "order": "asc",
                    "page_size": PAGE_SIZE,
                    "page": page,
                },
                verify=False,
            )
            if resp.status_code != 200:
                phantom.error("session_get playbook_run returned status {}".format(resp.status_code))
                break

            resp_json = resp.json()
            page_data = resp_json.get("data", [])
            for run in page_data:
                misc = run.get("misc") or {}
                parent_info = misc.get("parent_playbook_run") or {}
                run_name = parent_info.get("child_playbook_run_name", "")
                if run_name.startswith("rotation_") and run.get("status") in ("success", "failed"):
                    outputs = run.get("outputs") or []
                    if outputs:
                        try:
                            first_out = outputs[0]
                            parsed = json.loads(first_out) if isinstance(first_out, str) else first_out
                            child_runs_by_name[run_name] = parsed
                        except Exception:
                            pass

            if len(page_data) < PAGE_SIZE:
                break  # last page
    except Exception as e:
        phantom.error("Failed to read child run outputs via REST: {}".format(e))

    completed = len(child_runs_by_name)
    phantom.save_run_data(key="collect_results:completed", value=str(completed))
    phantom.debug("Rotation {}/{} complete".format(completed, total))

    if completed >= total:
        # Once-only guard: callbacks run sequentially in SOAR, but all may see
        # completed==total because REST query reflects final state for all of them.
        if phantom.get_run_data(key="collect_results:summary_done"):
            phantom.debug("Summary already written — skipping duplicate")
            return
        phantom.save_run_data(key="collect_results:summary_done", value="true")

        all_results = []
        _targets = []
        try:
            _targets = json.loads(phantom.get_run_data(key="dispatch_rotations:targets") or "[]")
        except Exception:
            pass

        for i in range(total):
            run_name = "rotation_{}".format(i)
            asset = _targets[i]["asset"] if i < len(_targets) else run_name
            result = child_runs_by_name.get(run_name)
            if result:
                all_results.append(result)
            else:
                all_results.append({"status": "unknown", "message": "No result received for {}".format(run_name), "target_asset": asset})

        phantom.save_run_data(key="collect_results:results", value=json.dumps(all_results))

        # Chain to build_summary explicitly (VPE edge fires before callbacks, so we call directly)
        build_summary(container=container)

    ################################################################################
    ## Custom Code End
    ################################################################################

    return


@phantom.playbook_block()
def build_summary(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("build_summary() called")

    build_summary__note_title = None
    build_summary__note_content = None
    build_summary__severity = None

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Sync-only code block (callback chain)
    _completed = int(phantom.get_run_data(key="collect_results:completed") or "0")
    _total = int(phantom.get_run_data(key="dispatch_rotations:total") or "0")
    if _completed < _total:
        return

    dispatched = phantom.get_run_data(key="dispatch_rotations:total") or "0"
    error = None
    try:
        error = json.loads(phantom.get_run_data(key="dispatch_rotations:error") or "null")
    except Exception:
        pass

    targets_info = []
    try:
        targets_info = json.loads(phantom.get_run_data(key="dispatch_rotations:targets") or "[]")
    except Exception:
        pass

    all_results = []
    try:
        all_results = json.loads(phantom.get_run_data(key="collect_results:results") or "[]")
    except Exception:
        pass

    note_lines = ["# CyberArk CCP Credential Rotation Summary"]
    note_lines.append("**Time:** {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    note_lines.append("**Dispatched:** {} rotation(s)".format(dispatched))

    if error:
        note_lines.append("**Error:** {}".format(error))

    if targets_info:
        note_lines.append("")
        note_lines.append("## Targets")
        for t in targets_info:
            target_desc = "- **{}** (safe={}, user_field={}, pwd_field={})".format(
                t.get("asset", "?"), t.get("safe", "?"),
                t.get("user_field", "?"), t.get("pwd_field", "?"))
            if t.get("address"):
                target_desc += " [address={}]".format(t["address"])
            note_lines.append(target_desc)

    if all_results:
        note_lines.append("")
        note_lines.append("## Results")
        for idx, r in enumerate(all_results):
            if isinstance(r, dict):
                status = r.get("status", "unknown")
                message = r.get("message", "")
                target = r.get("target_asset", "rotation_{}".format(idx))
                note_lines.append("- **{}**: {}  \u2014 {}".format(target, status, message))
            else:
                note_lines.append("- Rotation {}: {}".format(idx + 1, r))

    note_content = "\n".join(note_lines)
    note_title = "Credential Rotation - {}".format(datetime.now().strftime("%Y-%m-%d %H:%M"))

    if all_results:
        statuses = [r.get("status", "unknown") if isinstance(r, dict) else "unknown" for r in all_results]
        if all(s == "success" for s in statuses):
            sev = "low"
        elif any(s == "failed" for s in statuses):
            sev = "high"
        elif any(s in ("pending_recheck", "rotated (change pending)") for s in statuses):
            sev = "medium"
        else:
            sev = "medium"
    elif error:
        # Zero-targets discovery failure is a real failure, not a quiet no-op
        sev = "high"
    else:
        sev = "low"

    build_summary__note_title = note_title
    build_summary__note_content = note_content
    build_summary__severity = sev

    phantom.debug("Summary built: title='{}', severity='{}'".format(note_title, sev))

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.save_run_data(key="build_summary:note_title", value=json.dumps(build_summary__note_title))
    phantom.save_run_data(key="build_summary:note_content", value=json.dumps(build_summary__note_content))
    phantom.save_run_data(key="build_summary:severity", value=json.dumps(build_summary__severity))

    add_summary_note(container=container)

    return


@phantom.playbook_block()
def add_summary_note(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("add_summary_note() called")

    build_summary__note_title = json.loads(phantom.get_run_data(key="build_summary:note_title"))
    build_summary__note_content = json.loads(phantom.get_run_data(key="build_summary:note_content"))

    # Defense-in-depth against collect_results' non-atomic guard
    try:
        notes_url = phantom.build_phantom_rest_url("container", container.get("id"), "notes")
        resp = phantom.session_get(notes_url, verify=False)
        if resp.status_code == 200:
            notes = resp.json()
            if any((n.get("title") or "").startswith("Credential Rotation - ") for n in notes.get("data", [])):
                phantom.debug("Summary note already exists for this container — skipping duplicate")
                update_rotation_state(container=container)
                return
    except Exception as e:
        phantom.error("Failed to check for existing summary note: {}".format(e))

    # Sync add_note (callback chain)
    phantom.add_note(
        container=container,
        note_type="general",
        title=build_summary__note_title,
        content=build_summary__note_content,
    )

    phantom.debug("Summary note added")

    update_rotation_state(container=container)

    return


@phantom.playbook_block()
def update_rotation_state(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("update_rotation_state() called")

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Sync list read-merge-write (callback chain)
    STATE_LIST_NAME = "cyberark_ccp_rotation_state"

    targets_info = []
    try:
        targets_info = json.loads(phantom.get_run_data(key="dispatch_rotations:targets") or "[]")
    except Exception:
        pass

    all_results = []
    try:
        all_results = json.loads(phantom.get_run_data(key="collect_results:results") or "[]")
    except Exception:
        pass

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    event_id = str(container.get("id", ""))
    soar_base = phantom.get_base_url() or ""
    event_link = "{}/mission/{}".format(soar_base, event_id)

    try:
        state = {}
        read_success, _read_msg, rows = phantom.get_list(list_name=STATE_LIST_NAME)
        if read_success and rows:
            for row in rows:
                if row and len(row) >= 11 and row[0] != "asset":
                    state[row[0]] = row

        # Column order: vault-mapping (1-5) then status (6-11)
        for idx, r in enumerate(all_results):
            t = targets_info[idx] if idx < len(targets_info) else {}
            asset = t.get("asset", "?")
            status = r.get("status", "unknown") if isinstance(r, dict) else "unknown"
            message = r.get("message", "") if isinstance(r, dict) else str(r)
            state[asset] = [
                asset, t.get("safe", "?"), t.get("user_field", "username"), t.get("pwd_field", "password"),
                t.get("address", ""), t.get("connector", ""), t.get("username", "?"),
                status, message[:200], now_str, event_link,
            ]

        header = [
            "asset", "safe", "user_field", "pwd_field", "address",
            "connector", "username", "status", "message", "last_rotated", "event_link",
        ]
        content = [header] + [state[k] for k in sorted(state)]

        phantom.set_list(list_name=STATE_LIST_NAME, values=content)
    except Exception as e:
        phantom.debug("Failed to update rotation state: {}".format(str(e)))

    phantom.debug("Rotation state updated")

    ################################################################################
    ## Custom Code End
    ################################################################################

    update_severity(container=container)

    return


@phantom.playbook_block()
def update_severity(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("update_severity() called")

    build_summary__severity = json.loads(phantom.get_run_data(key="build_summary:severity") or '"low"')

    # Sync set_severity (no native equivalent, callback chain)
    phantom.set_severity(container=container, severity=build_summary__severity)

    phantom.debug("Container severity set to '{}'".format(build_summary__severity))

    return


@phantom.playbook_block()
def format_no_targets_note(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("format_no_targets_note() called")

    template = (
        "No assets found with the 'cyberark_ccp' description prefix for CyberArk credential rotation.\n\n"
        "For each target asset, set the asset Description field to:\n\n"
        "  `cyberark_ccp:safe=<safe>,user_field=<user_field>,pwd_field=<pwd_field>[,address=<address>]`\n\n"
        "Example:\n"
        "  `cyberark_ccp:safe=LinuxSafe,user_field=username,pwd_field=password,address=srv01.corp`\n\n"
        "Where:\n"
        "- **safe** = CyberArk safe name containing the credential\n"
        "- **user_field** = asset config key that holds the username (e.g. 'username')\n"
        "- **pwd_field** = asset config key to update with the rotated password (e.g. 'password')\n"
        "- **address** = (optional) CyberArk address filter for accounts sharing the same username\n\n"
        "Rotation state is tracked in the 'cyberark_ccp_rotation_state' custom list."
    )

    phantom.format(container=container, template=template, parameters=[], name="format_no_targets_note")

    add_note_no_targets(container=container)

    return


@phantom.playbook_block()
def add_note_no_targets(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("add_note_no_targets() called")

    format_no_targets_note = phantom.get_format_data(name="format_no_targets_note")

    parameters = []
    parameters.append({
        "title": "Credential Rotation - No Targets",
        "content": format_no_targets_note,
    })

    phantom.act("add note", parameters=parameters, name="add_note_no_targets", assets=["soar6"])

    return


def on_finish(container, summary):
    phantom.debug("on_finish() called")
    return
