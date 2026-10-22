"""
Refreshes the password of each asset listed in cyberark_ccp_rotation_state from CyberArk CCP: writes it into the asset&#39;s password field, tests the asset&#39;s connectivity, and records the result in the list, one note and the container severity.
"""


import phantom.rules as phantom
import json
from datetime import datetime, timedelta


################################################################################
## Global Custom Code Start
################################################################################
################################################################################
################################################################################
################################################################################

################################################################################
################################################################################
################################################################################
################################################################################
## Global Custom Code End
################################################################################

@phantom.playbook_block()
def on_start(container):
    phantom.debug('on_start() called')

    # call 'read_targets' block
    read_targets(container=container)

    return

@phantom.playbook_block()
def read_targets(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("read_targets() called")

    ################################################################################
    # Read the targets from the list and the CyberArk accounts to query.
    ################################################################################

    parameters = []

    parameters.append({
        "list_name": "cyberark_ccp_rotation_state",
    })

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Write your custom code here...

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.custom_function(custom_function="local/cyberark_ccp_get_targets", parameters=parameters, name="read_targets", callback=anything_to_query)

    return


@phantom.playbook_block()
def anything_to_query(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("anything_to_query() called")

    ################################################################################
    # Query CyberArk only when at least one account is to be queried.
    ################################################################################

    # collect filtered artifact ids and results for 'if' condition 1
    matched_artifacts_1, matched_results_1 = phantom.condition(
        container=container,
        conditions=[
            ["read_targets:custom_function_result.data.has_queries", "==", "yes"]
        ],
        conditions_dps=[
            ["read_targets:custom_function_result.data.has_queries", "==", "yes"]
        ],
        name="anything_to_query:condition_1",
        delimiter=",")

    # call connected blocks if filtered artifacts or results
    if matched_artifacts_1 or matched_results_1:
        get_secrets(action=action, success=success, container=container, results=results, handle=handle, filtered_artifacts=matched_artifacts_1, filtered_results=matched_results_1)

    # collect filtered artifact ids and results for 'if' condition 2
    matched_artifacts_2, matched_results_2 = phantom.condition(
        container=container,
        conditions=[
            ["read_targets:custom_function_result.data.has_queries", "==", "no"]
        ],
        conditions_dps=[
            ["read_targets:custom_function_result.data.has_queries", "==", "no"]
        ],
        name="anything_to_query:condition_2",
        delimiter=",")

    # call connected blocks if filtered artifacts or results
    if matched_artifacts_2 or matched_results_2:
        report_nothing_queried(action=action, success=success, container=container, results=results, handle=handle, filtered_artifacts=matched_artifacts_2, filtered_results=matched_results_2)

    return


@phantom.playbook_block()
def get_secrets(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("get_secrets() called")

    # phantom.debug('Action: {0} {1}'.format(action['name'], ('SUCCEEDED' if success else 'FAILED')))

    ################################################################################
    # Ask CyberArk CCP for each account's password, one result per account.
    ################################################################################

    read_targets__result = phantom.collect2(container=container, datapath=["read_targets:custom_function_result.data.safes","read_targets:custom_function_result.data.addresses","read_targets:custom_function_result.data.usernames"])

    parameters = []

    # build parameters list for 'get_secrets' call
    for read_targets__result_item in read_targets__result:
        if read_targets__result_item[0] is not None and read_targets__result_item[2] is not None:
            parameters.append({
                "safe": read_targets__result_item[0],
                "address": read_targets__result_item[1],
                "username": read_targets__result_item[2],
            })

    ################################################################################
    ## Custom Code Start
    ################################################################################
    ################################################################################
    ################################################################################
    ################################################################################

    # One parameter set per CyberArk account. The bindings above arrive as one
    # set holding three parallel lists (safes, usernames, addresses), so they
    # are unzipped here; address is sent only when set. A VPE save keeps this
    # section and rebuilds the code above from the bindings.
    bound = parameters[0] if parameters else {}
    parameters = []
    for safe, username, address in zip(bound.get("safe") or [], bound.get("username") or [], bound.get("address") or []):
        parameter = {"safe": safe, "username": username}
        if address:
            parameter["address"] = address
        parameters.append(parameter)

    ################################################################################
    ################################################################################
    ################################################################################
    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.act("get secret", parameters=parameters, name="get_secrets", assets=["cyberark ccp mock"], callback=classify_secrets)

    return


@phantom.playbook_block()
def classify_secrets(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("classify_secrets() called")

    ################################################################################
    # Classify each answer: write, pending (APPAP282E) or failed.
    ################################################################################

    get_secrets_result_data = phantom.collect2(container=container, datapath=["get_secrets:action_result.parameter.safe","get_secrets:action_result.message","get_secrets:action_result.status","get_secrets:action_result.parameter.address","get_secrets:action_result.parameter.username","get_secrets:action_result.data.*.password_change_in_process","get_secrets:action_result.parameter.context.artifact_id"], action_results=results)
    read_targets__result = phantom.collect2(container=container, datapath=["read_targets:custom_function_result.data.targets_json"])

    get_secrets_parameter_safe = [item[0] for item in get_secrets_result_data]
    get_secrets_result_message = [item[1] for item in get_secrets_result_data]
    get_secrets_result_item_2 = [item[2] for item in get_secrets_result_data]
    get_secrets_parameter_address = [item[3] for item in get_secrets_result_data]
    get_secrets_parameter_username = [item[4] for item in get_secrets_result_data]
    get_secrets_result_item_5 = [item[5] for item in get_secrets_result_data]

    parameters = []

    # build parameters list for 'classify_secrets' call
    for read_targets__result_item in read_targets__result:
        parameters.append({
            "safes": get_secrets_parameter_safe,
            "messages": get_secrets_result_message,
            "statuses": get_secrets_result_item_2,
            "addresses": get_secrets_parameter_address,
            "usernames": get_secrets_parameter_username,
            "change_flags": get_secrets_result_item_5,
            "targets_json": read_targets__result_item[0],
        })

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Write your custom code here...

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.custom_function(custom_function="local/cyberark_ccp_classify_secrets", parameters=parameters, name="classify_secrets", callback=anything_to_write)

    return


@phantom.playbook_block()
def anything_to_write(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("anything_to_write() called")

    ################################################################################
    # Write passwords only when CyberArk returned at least one.
    ################################################################################

    # collect filtered artifact ids and results for 'if' condition 1
    matched_artifacts_1, matched_results_1 = phantom.condition(
        container=container,
        conditions=[
            ["classify_secrets:custom_function_result.data.has_writes", "==", "yes"]
        ],
        conditions_dps=[
            ["classify_secrets:custom_function_result.data.has_writes", "==", "yes"]
        ],
        name="anything_to_write:condition_1",
        delimiter=",")

    # call connected blocks if filtered artifacts or results
    if matched_artifacts_1 or matched_results_1:
        write_passwords(action=action, success=success, container=container, results=results, handle=handle, filtered_artifacts=matched_artifacts_1, filtered_results=matched_results_1)

    # collect filtered artifact ids and results for 'if' condition 2
    matched_artifacts_2, matched_results_2 = phantom.condition(
        container=container,
        conditions=[
            ["classify_secrets:custom_function_result.data.has_writes", "==", "no"]
        ],
        conditions_dps=[
            ["classify_secrets:custom_function_result.data.has_writes", "==", "no"]
        ],
        name="anything_to_write:condition_2",
        delimiter=",")

    # call connected blocks if filtered artifacts or results
    if matched_artifacts_2 or matched_results_2:
        report_nothing_written(action=action, success=success, container=container, results=results, handle=handle, filtered_artifacts=matched_artifacts_2, filtered_results=matched_results_2)

    return


@phantom.playbook_block()
def write_passwords(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("write_passwords() called")

    ################################################################################
    # Write each password into its asset's password field only.
    ################################################################################

    classify_secrets__result = phantom.collect2(container=container, datapath=["classify_secrets:custom_function_result.data.write_assets","classify_secrets:custom_function_result.data.write_fields"])

    parameters = []

    # build parameters list for 'write_passwords' call
    for classify_secrets__result_item in classify_secrets__result:
        parameters.append({
            "asset": classify_secrets__result_item[0],
            "configuration_updates": classify_secrets__result_item[1],
        })

    ################################################################################
    ## Custom Code Start
    ################################################################################
    ################################################################################
    ################################################################################
    ################################################################################

    # One parameter set per asset to write: {pwd_field: password}. The
    # password is read here from get_secrets' result, so it never passes
    # through a block output.
    def account_key(safe, username, address):
        return "|".join(str(value or "") for value in (safe, username, address))

    secrets = {}
    for row in phantom.collect2(
        container=container,
        datapath=[
            "get_secrets:action_result.parameter.safe",
            "get_secrets:action_result.parameter.username",
            "get_secrets:action_result.parameter.address",
            "get_secrets:action_result.data",
        ],
    ):
        for record in row[3] or []:
            if isinstance(record, dict) and record.get("password"):
                secrets[account_key(row[0], row[1], row[2])] = record["password"]
                break

    classified = phantom.collect2(container=container, datapath=["classify_secrets:custom_function_result.data.targets_json"])
    targets = json.loads((classified[0][0] if classified else None) or "[]")
    parameters = []
    for target in targets:
        if target.get("write"):
            secret = secrets.get(account_key(target["safe"], target["username"], target["address"]))
            # No password in the result: an empty update makes the function
            # raise, and start_tests reports the asset as not written.
            updates = {target["pwd_field"]: secret} if secret else {}
            parameters.append({"asset": target["asset"], "configuration_updates": json.dumps(updates)})

    ################################################################################
    ################################################################################
    ################################################################################
    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.custom_function(custom_function="local/cyberark_ccp_update_asset", parameters=parameters, name="write_passwords", callback=start_tests)

    return


@phantom.playbook_block()
def start_tests(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("start_tests() called")

    ################################################################################
    # Start test connectivity on each written asset.
    ################################################################################

    id_value = container.get("id", None)
    classify_secrets__result = phantom.collect2(container=container, datapath=["classify_secrets:custom_function_result.data.targets_json"])
    write_passwords__result = phantom.collect2(container=container, datapath=["write_passwords:custom_function_result.data.success","write_passwords:custom_function_result.data.message","write_passwords:custom_function_result.data.asset_name"])

    write_passwords_data_success = [item[0] for item in write_passwords__result]
    write_passwords_data_message = [item[1] for item in write_passwords__result]
    write_passwords_data_asset_name = [item[2] for item in write_passwords__result]

    parameters = []

    # build parameters list for 'start_tests' call
    for classify_secrets__result_item in classify_secrets__result:
        parameters.append({
            "container_id": id_value,
            "targets_json": classify_secrets__result_item[0],
            "wait_seconds": 60,
            "write_success": write_passwords_data_success,
            "write_messages": write_passwords_data_message,
            "written_assets": write_passwords_data_asset_name,
            "test_connectivity": True,
        })

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Write your custom code here...

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.custom_function(custom_function="local/cyberark_ccp_start_tests", parameters=parameters, name="start_tests", callback=wait_for_tests)

    return


@phantom.playbook_block()
def wait_for_tests(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("wait_for_tests() called")

    # phantom.debug('Action: {0} {1}'.format(action['name'], ('SUCCEEDED' if success else 'FAILED')))

    ################################################################################
    # Give the connectivity tests time to finish.
    ################################################################################

    start_tests__result = phantom.collect2(container=container, datapath=["start_tests:custom_function_result.data.wait_seconds"])

    parameters = []

    # build parameters list for 'wait_for_tests' call
    for start_tests__result_item in start_tests__result:
        if start_tests__result_item[0] is not None:
            parameters.append({
                "sleep_seconds": start_tests__result_item[0],
            })

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Write your custom code here...

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.act("no op", parameters=parameters, name="wait_for_tests", assets=["soar8"], callback=report)

    return


@phantom.playbook_block()
def report(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("report() called")

    ################################################################################
    # Write the result to the list, one note and the container severity.
    ################################################################################

    id_value = container.get("id", None)
    start_tests__result = phantom.collect2(container=container, datapath=["start_tests:custom_function_result.data.targets_json"])

    parameters = []

    # build parameters list for 'report' call
    for start_tests__result_item in start_tests__result:
        parameters.append({
            "list_name": "cyberark_ccp_rotation_state",
            "container_id": id_value,
            "targets_json": start_tests__result_item[0],
        })

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Write your custom code here...

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.custom_function(custom_function="local/cyberark_ccp_report", parameters=parameters, name="report")

    return


@phantom.playbook_block()
def report_nothing_written(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("report_nothing_written() called")

    ################################################################################
    # Write the result when no password is to be written.
    ################################################################################

    id_value = container.get("id", None)
    classify_secrets__result = phantom.collect2(container=container, datapath=["classify_secrets:custom_function_result.data.targets_json"])

    parameters = []

    # build parameters list for 'report_nothing_written' call
    for classify_secrets__result_item in classify_secrets__result:
        parameters.append({
            "list_name": "cyberark_ccp_rotation_state",
            "container_id": id_value,
            "targets_json": classify_secrets__result_item[0],
        })

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Write your custom code here...

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.custom_function(custom_function="local/cyberark_ccp_report", parameters=parameters, name="report_nothing_written")

    return


@phantom.playbook_block()
def report_nothing_queried(action=None, success=None, container=None, results=None, handle=None, filtered_artifacts=None, filtered_results=None, custom_function=None, loop_state_json=None, **kwargs):
    phantom.debug("report_nothing_queried() called")

    ################################################################################
    # Write the result when no CyberArk account is to be queried.
    ################################################################################

    id_value = container.get("id", None)
    read_targets__result = phantom.collect2(container=container, datapath=["read_targets:custom_function_result.data.targets_json"])

    parameters = []

    # build parameters list for 'report_nothing_queried' call
    for read_targets__result_item in read_targets__result:
        parameters.append({
            "list_name": "cyberark_ccp_rotation_state",
            "container_id": id_value,
            "targets_json": read_targets__result_item[0],
        })

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # Write your custom code here...

    ################################################################################
    ## Custom Code End
    ################################################################################

    phantom.custom_function(custom_function="local/cyberark_ccp_report", parameters=parameters, name="report_nothing_queried")

    return


@phantom.playbook_block()
def on_finish(container, summary):
    phantom.debug("on_finish() called")

    ################################################################################
    ## Custom Code Start
    ################################################################################

    # This function is called after all actions are completed.
    # summary of all the action and/or all details of actions
    # can be collected here.

    # summary_json = phantom.get_summary()
    # if 'result' in summary_json:
        # for action_result in summary_json['result']:
            # if 'action_run_id' in action_result:
                # action_results = phantom.get_action_results(action_run_id=action_result['action_run_id'], result_data=False, flatten=False)
                # phantom.debug(action_results)

    ################################################################################
    ## Custom Code End
    ################################################################################

    return
