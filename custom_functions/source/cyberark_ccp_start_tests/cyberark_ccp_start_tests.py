def cyberark_ccp_start_tests(targets_json=None, written_assets=None, write_success=None, write_messages=None, test_connectivity=None, wait_seconds=None, container_id=None, **kwargs):
    """
    Start test connectivity on each asset whose password was written.
    
    Args:
        targets_json: targets_json of cyberark_ccp_classify_secrets.
        written_assets: asset_name of each cyberark_ccp_update_asset result.
        write_success: success of each cyberark_ccp_update_asset result.
        write_messages: message of each cyberark_ccp_update_asset result.
        test_connectivity: true: test each written asset; false: only write (status written).
        wait_seconds: Seconds the next block waits for the tests (default 60).
        container_id (CEF type: phantom container id): Container the tests run on.
    
    Returns a JSON-serializable object that implements the configured data paths:
        targets_json: The targets, with the written ones marked and their test run ids.
        test_count: Number of tests started.
        wait_seconds: wait_seconds when a test started, else 1.
    """
    ############################ Custom Code Goes Below This Line #################################
    import json
    import phantom.rules as phantom

    def as_list(value):
        return value if isinstance(value, list) else [value]

    # One update result per write, matched by the asset name it echoes. A write
    # that raised has no result: it failed.
    written = {}
    for asset, success, message in zip(as_list(written_assets), as_list(write_success), as_list(write_messages)):
        if asset:
            written[asset] = {"success": success is True or str(success).lower() == "true", "message": message or ""}

    run_tests = test_connectivity is True or str(test_connectivity).strip().lower() == "true"
    container_id = int(container_id[0] if isinstance(container_id, (list, tuple)) else container_id)

    targets = json.loads(targets_json or "[]")
    tests = 0
    for target in targets:
        if not target.get("write"):
            continue
        write = written.get(target["asset"])
        if not write or not write["success"]:
            target["status"] = "failed"
            target["message"] = "Password not written: {}".format(
                (write or {}).get("message") or "the update raised; see this playbook run")
            continue
        target["written"] = True
        if not run_tests:
            target["status"], target["message"] = "written", "Test connectivity is switched off"
            continue
        # The asset is known only at run time, so the test goes through REST
        # (a native action block runs on an asset chosen in the editor).
        response = phantom.requests.post(
            uri=phantom.build_phantom_rest_url("action_run"),
            data=json.dumps({
                "action": "test connectivity",
                "name": "test connectivity {}".format(target["asset"]),
                "type": "generic",
                "container_id": container_id,
                "targets": [{"assets": [target["asset"]], "parameters": [{}], "app_id": target["app_id"]}],
            }),
            verify=False,
        )
        target["test_run"] = response.json().get("action_run_id") if response.status_code == 200 else None
        if target["test_run"]:
            tests += 1
        else:
            target["status"] = "written (no test result)"
            target["message"] = "Test connectivity did not start: HTTP {}".format(response.status_code)

    outputs = {
        "targets_json": json.dumps(targets),
        "test_count": tests,
        "wait_seconds": int(wait_seconds or 60) if tests else 1,
    }

    # Return a JSON-serializable object
    assert json.dumps(outputs)
    return outputs
