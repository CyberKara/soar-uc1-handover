"""
Credential Rotation - CyberArk CCP

Fetches fresh credentials from CyberArk CCP vault and updates a target SOAR
asset's configuration. Called as a utility playbook by cyberark_rotation_orchestrator.
Flow/architecture detail: docs/uc1_dev_notes.md

Inputs:
  - target_asset: Name or ID of the target asset to update
  - safe: CyberArk safe name containing the credential
  - username: CyberArk username to look up
  - address: (optional) CyberArk address filter
  - pwd_field: Asset configuration field that holds the password (default: password)
  - user_field: Configuration field that holds the username on the target asset (default: username)

Output:
  - status: JSON with rotation result details
"""


import phantom.rules as phantom
import json
from datetime import datetime


@phantom.playbook_block()
def on_start(container):
    phantom.debug('on_start() called')

    validate_inputs(container=container)

    return


@phantom.playbook_block()
def validate_inputs(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("validate_inputs() called")

    playbook_input_safe = phantom.collect2(container=container, datapath=["playbook_input:safe"])
    playbook_input_username = phantom.collect2(container=container, datapath=["playbook_input:username"])

    safe_value = (playbook_input_safe[0][0] if playbook_input_safe else None) or ""
    username_value = (playbook_input_username[0][0] if playbook_input_username else None) or ""

    found_match_1 = phantom.decision(
        container=container,
        conditions=[
            [safe_value, "!=", ""]
        ])

    found_match_2 = phantom.decision(
        container=container,
        conditions=[
            [username_value, "!=", ""]
        ])

    if found_match_1 and found_match_2:
        get_secret_from_vault(action=action, success=success, container=container, results=results, handle=handle)
        return

    phantom.error("Missing required inputs: safe and username")
    phantom.save_run_data(key="rotation_error", value=json.dumps("Missing required inputs: safe and username"))
    format_error(action=action, success=success, container=container, results=results, handle=handle)

    return


@phantom.playbook_block()
def get_secret_from_vault(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("get_secret_from_vault() called")

    playbook_input_safe = phantom.collect2(container=container, datapath=["playbook_input:safe"])
    playbook_input_username = phantom.collect2(container=container, datapath=["playbook_input:username"])
    playbook_input_address = phantom.collect2(container=container, datapath=["playbook_input:address"])

    safe_value = playbook_input_safe[0][0] if playbook_input_safe else None
    username_value = playbook_input_username[0][0] if playbook_input_username else None
    address_value = playbook_input_address[0][0] if playbook_input_address and playbook_input_address[0][0] else None

    parameters = []

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Plain native-action passthrough
    param = {
        "safe": safe_value,
        "username": username_value,
    }
    if address_value:
        param["address"] = address_value
    parameters.append(param)

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.act("get secret", parameters=parameters, name="get_secret_from_vault", assets=["cyberark ccp mock"], callback=build_config_update)

    return


@phantom.playbook_block()
def build_config_update(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("build_config_update() called")

    build_config_update__error = ""
    build_config_update__config_json = None
    build_config_update__target_asset = None
    build_config_update__password_change_in_process = False

    ################################################################################
    ## Custom Code Start
    ################################################################################

    get_secret_result = phantom.collect2(
        container=container,
        datapath=[
            "get_secret_from_vault:action_result.status",
            "get_secret_from_vault:action_result.data.*.password",
            "get_secret_from_vault:action_result.message",
            "get_secret_from_vault:action_result.data.*.password_change_in_process",
        ]
    )

    playbook_input_pwd_field = phantom.collect2(container=container, datapath=["playbook_input:pwd_field"])
    pwd_field = "password"
    if playbook_input_pwd_field and playbook_input_pwd_field[0][0]:
        pwd_field = playbook_input_pwd_field[0][0]

    playbook_input_target_asset = phantom.collect2(container=container, datapath=["playbook_input:target_asset"])
    if playbook_input_target_asset and playbook_input_target_asset[0][0]:
        build_config_update__target_asset = playbook_input_target_asset[0][0]
    else:
        build_config_update__error = "Missing required input: target_asset"
        phantom.error(build_config_update__error)

    if not build_config_update__error:
        cyberark_ok = False
        password = None
        if get_secret_result:
            status = get_secret_result[0][0]
            password = get_secret_result[0][1]
            message = get_secret_result[0][2]
            change_in_process = get_secret_result[0][3]
            if status == "success" and password:
                cyberark_ok = True
                if change_in_process:
                    build_config_update__password_change_in_process = True
                    phantom.debug("CyberArk password change in progress for '{}'".format(build_config_update__target_asset))
                else:
                    phantom.debug("CyberArk get_secret succeeded for '{}'".format(build_config_update__target_asset))
            else:
                phantom.debug("CyberArk get_secret failed: {}".format(message or "unknown error"))
        else:
            phantom.debug("CyberArk get_secret returned no results")

        if cyberark_ok:
            build_config_update__config_json = json.dumps({pwd_field: password})
        else:
            build_config_update__error = "CyberArk failed: {}".format(get_secret_result[0][2] if get_secret_result else "no response")
            phantom.error(build_config_update__error)

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.save_run_data(key="build_config_update:config_json", value=json.dumps(build_config_update__config_json))
    phantom.save_run_data(key="build_config_update:target_asset", value=json.dumps(build_config_update__target_asset))
    phantom.save_run_data(key="build_config_update:error", value=json.dumps(build_config_update__error))
    phantom.save_run_data(key="build_config_update:password_change_in_process", value=json.dumps(build_config_update__password_change_in_process))

    update_decision(container=container)

    return


@phantom.playbook_block()
def update_decision(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("update_decision() called")

    build_config_update__error = json.loads(phantom.get_run_data(key="build_config_update:error"))

    found_match_1 = phantom.decision(
        container=container,
        conditions=[
            [build_config_update__error, "==", ""]
        ])

    if found_match_1:
        update_target_asset(action=action, success=success, container=container, results=results, handle=handle)
        return

    format_error(action=action, success=success, container=container, results=results, handle=handle)

    return


@phantom.playbook_block()
def update_target_asset(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("update_target_asset() called")

    build_config_update__target_asset = json.loads(phantom.get_run_data(key="build_config_update:target_asset"))
    build_config_update__config_json = json.loads(phantom.get_run_data(key="build_config_update:config_json"))

    parameters = []

    parameters.append({
        "asset": build_config_update__target_asset,
        "configuration_updates": build_config_update__config_json,
    })

    phantom.debug("Updating asset '{}' configuration".format(build_config_update__target_asset))

    phantom.custom_function(custom_function="local/cyberark_asset_update_configuration", parameters=parameters, name="update_target_asset", callback=run_test_connectivity)

    return


@phantom.playbook_block()
def run_test_connectivity(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("run_test_connectivity() called")

    run_test_connectivity__output = None

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Sync REST action_run + poll: phantom.act("test connectivity") + callback would race with on_finish
    import time

    # Read target_asset from playbook input (not from CF output which can be empty)
    playbook_input_target_asset = phantom.collect2(container=container, datapath=["playbook_input:target_asset"])
    playbook_input_safe = phantom.collect2(container=container, datapath=["playbook_input:safe"])
    playbook_input_username = phantom.collect2(container=container, datapath=["playbook_input:username"])
    target_asset = playbook_input_target_asset[0][0] if playbook_input_target_asset else None

    update_result = phantom.collect2(
        container=container,
        datapath=[
            "update_target_asset:custom_function_result.data.success",
            "update_target_asset:custom_function_result.data.message",
        ]
    )

    if not update_result or not update_result[0][0]:
        update_msg = update_result[0][1] if update_result else "No result from asset_update_configuration"
        error_output = {
            "status": "failed",
            "message": "Asset update failed: {}".format(update_msg),
            "target_asset": target_asset,
            "password_change_in_process": False,
            "timestamp": datetime.now().isoformat(),
        }
        run_test_connectivity__output = error_output
        phantom.save_run_data(key="run_test_connectivity:output", value=json.dumps(run_test_connectivity__output))
        phantom.error("Asset update failed: {}".format(update_msg))
        return

    phantom.debug("Asset '{}' updated successfully, running test connectivity".format(target_asset))

    test_status = None
    test_message = ""
    try:
        # Look up asset's app_id (required by POST /rest/action_run)
        asset_resp = phantom.requests.get(
            uri=phantom.build_phantom_rest_url("asset") + "?_filter_name=\"{}\"&page_size=1".format(target_asset),
            verify=False,
        )
        asset_data = asset_resp.json().get("data", [])
        app_id = asset_data[0].get("app") if asset_data else None

        if not app_id:
            phantom.error("Cannot find app_id for asset '{}'".format(target_asset))
        else:
            resp = phantom.requests.post(
                uri=phantom.build_phantom_rest_url("action_run"),
                data=json.dumps({
                    "action": "test connectivity",
                    "name": "test_conn_{}".format(target_asset),
                    "type": "generic",
                    "container_id": container["id"],
                    "targets": [{"assets": [target_asset], "parameters": [{}], "app_id": app_id}],
                }),
                verify=False,
            )
            action_run_id = resp.json().get("action_run_id")
            if action_run_id:
                for _ in range(30):
                    time.sleep(2)
                    check = phantom.requests.get(
                        uri=phantom.build_phantom_rest_url("action_run", action_run_id),
                        verify=False,
                    )
                    check_data = check.json()
                    if check_data.get("status") in ("success", "failed"):
                        test_status = check_data.get("status")
                        test_message = check_data.get("message", "")
                        break
    except Exception as e:
        phantom.error("Test connectivity REST call failed: {}".format(e))

    password_change_in_process = False
    try:
        password_change_in_process = json.loads(phantom.get_run_data(key="build_config_update:password_change_in_process") or "false")
    except Exception:
        pass

    if test_status is None:
        rotation_status = "rotated (no test result)"
        rotation_message = "Credential updated on '{}'. Connectivity test returned no result.".format(target_asset)
    elif test_status == "success":
        rotation_status = "success"
        rotation_message = "Credential rotation complete. Asset '{}' updated and connectivity verified.".format(target_asset)
    else:
        rotation_status = "rotated (connectivity failed)"
        rotation_message = "Credential updated on '{}'. Connectivity test failed: {}".format(target_asset, test_message)

    if password_change_in_process:
        rotation_status = "rotated (change pending)"
        rotation_message += " [CyberArk password change in progress \u2014 updated with current password, scheduled for recheck]"

    output = {
        "status": rotation_status,
        "message": rotation_message,
        "target_asset": target_asset,
        "cyberark_safe": playbook_input_safe[0][0] if playbook_input_safe else None,
        "cyberark_username": playbook_input_username[0][0] if playbook_input_username else None,
        "password_change_in_process": password_change_in_process,
        "timestamp": datetime.now().isoformat(),
    }

    phantom.debug("Rotation result: {}".format(json.dumps(output)))
    run_test_connectivity__output = output

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.save_run_data(key="run_test_connectivity:output", value=json.dumps(run_test_connectivity__output))

    return


@phantom.playbook_block()
def format_error(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, **kwargs):
    phantom.debug("format_error() called")

    format_error__output = None

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Error classification: 2-level run_data fallback, APPAP282E substring match, pending_recheck vs failed
    error_msg = None
    try:
        error_msg = json.loads(phantom.get_run_data(key="build_config_update:error"))
    except Exception:
        pass

    if not error_msg:
        try:
            error_msg = json.loads(phantom.get_run_data(key="rotation_error"))
        except Exception:
            error_msg = "Unknown error during credential rotation"

    playbook_input_target_asset = phantom.collect2(container=container, datapath=["playbook_input:target_asset"])
    playbook_input_safe = phantom.collect2(container=container, datapath=["playbook_input:safe"])
    playbook_input_username = phantom.collect2(container=container, datapath=["playbook_input:username"])

    is_password_change = error_msg and "password change in progress" in error_msg.lower()

    if is_password_change:
        rotation_status = "pending_recheck"
        phantom.debug("CyberArk password change in progress \u2014 flagged for recheck")
    else:
        rotation_status = "failed"
        phantom.error("Rotation failed: {}".format(error_msg))

    format_error__output = {
        "status": rotation_status,
        "message": error_msg,
        "target_asset": playbook_input_target_asset[0][0] if playbook_input_target_asset else None,
        "cyberark_safe": playbook_input_safe[0][0] if playbook_input_safe else None,
        "cyberark_username": playbook_input_username[0][0] if playbook_input_username else None,
        "password_change_in_process": is_password_change,
        "timestamp": datetime.now().isoformat(),
    }

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.save_run_data(key="format_error:output", value=json.dumps(format_error__output))

    return


def on_finish(container, summary):
    phantom.debug("on_finish() called")

    ################################################################################
    ## Custom Code Start
    ################################################################################

    run_test_connectivity__output = None
    format_error__output = None
    try:
        run_test_connectivity__output = json.loads(phantom.get_run_data(key="run_test_connectivity:output"))
    except Exception:
        pass
    try:
        format_error__output = json.loads(phantom.get_run_data(key="format_error:output"))
    except Exception:
        pass

    output = run_test_connectivity__output or format_error__output or {"status": "failed", "message": "Playbook completed without result"}

    phantom.save_playbook_output_data(output=output)

    target_key = str(output.get("target_asset") or "unknown")
    phantom.save_run_data(key="cred_rot_result:{}".format(target_key), value=json.dumps(output))

    phantom.debug("Credential rotation finished: {}".format(json.dumps(output)))

    # Create recheck artifact if password change in progress (APPAP282E)
    if output.get("password_change_in_process") or output.get("status") == "pending_recheck":
        try:
            playbook_input_safe = phantom.collect2(container=container, datapath=["playbook_input:safe"])
            playbook_input_username = phantom.collect2(container=container, datapath=["playbook_input:username"])
            playbook_input_address = phantom.collect2(container=container, datapath=["playbook_input:address"])
            playbook_input_pwd_field = phantom.collect2(container=container, datapath=["playbook_input:pwd_field"])
            playbook_input_user_field = phantom.collect2(container=container, datapath=["playbook_input:user_field"])

            rotation_params = {
                "safe": playbook_input_safe[0][0] if playbook_input_safe else "",
                "username": playbook_input_username[0][0] if playbook_input_username else "",
                "address": (playbook_input_address[0][0] if playbook_input_address and playbook_input_address[0][0] else ""),
                "pwd_field": (playbook_input_pwd_field[0][0] if playbook_input_pwd_field and playbook_input_pwd_field[0][0] else "password"),
                "user_field": (playbook_input_user_field[0][0] if playbook_input_user_field and playbook_input_user_field[0][0] else "username"),
            }

            target_asset = output.get("target_asset", "unknown")

            cef_data = {
                "message": "Recheck request for {}".format(target_asset),
                "cs1": target_asset,
                "cs1Label": "target_asset",
                "cn1": 1,
                "cn1Label": "attempt",
                "cs2": json.dumps(rotation_params),
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
            phantom.debug("Recheck artifact created: success={}, id={}".format(success_flag, art_id))
        except Exception as e:
            phantom.error("Failed to create recheck artifact: {}".format(e))

    ################################################################################
    ## Custom Code End
    ################################################################################

    return
