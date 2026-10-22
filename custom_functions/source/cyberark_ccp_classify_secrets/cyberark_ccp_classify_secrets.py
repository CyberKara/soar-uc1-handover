def cyberark_ccp_classify_secrets(targets_json=None, safes=None, usernames=None, addresses=None, statuses=None, messages=None, change_flags=None, **kwargs):
    """
    Classify each target from its get secret result: write, pending (APPAP282E) or failed.
    
    Args:
        targets_json: targets_json of cyberark_ccp_get_targets.
        safes: get secret action_result.parameter.safe.
        usernames: get secret action_result.parameter.username.
        addresses: get secret action_result.parameter.address.
        statuses: get secret action_result.status.
        messages: get secret action_result.message.
        change_flags: get secret action_result.data.*.password_change_in_process.
    
    Returns a JSON-serializable object that implements the configured data paths:
        targets_json: The targets, each with write true, or status pending / failed and a message.
        has_writes: yes when at least one password is to be written, else no.
        write_count: Number of passwords to write.
        write_assets: Asset of each password to write.
        write_fields: Password field of each asset to write.
    """
    ############################ Custom Code Goes Below This Line #################################
    import json
    import phantom.rules as phantom

    def as_list(value):
        return value if isinstance(value, list) else [value]

    def is_true(value):
        # CCP's PasswordChangeInProcess is documented as a bool; a "True" string reads the same
        return value is True or str(value).strip().lower() == "true"

    def key(safe, username, address):
        return "|".join(str(value or "") for value in (safe, username, address))

    # One row per get secret result (the inputs are parallel lists). The
    # password is not an input: the write block reads it from the action result.
    results = {}
    rows = zip(as_list(safes), as_list(usernames), as_list(addresses),
               as_list(statuses), as_list(messages), as_list(change_flags))
    for safe, username, address, status, message, change in rows:
        entry = results.setdefault(key(safe, username, address), {"status": status, "message": message or "", "change": False})
        entry["change"] = entry["change"] or is_true(change)

    targets = json.loads(targets_json or "[]")
    for target in targets:
        if target["status"]:
            continue
        result = results.get(key(target["safe"], target["username"], target["address"]))
        if not result:
            # SOAR refused the query before dispatch: no action result exists.
            target["status"] = "failed"
            target["message"] = "SOAR did not run get secret; the reason is in this playbook run"
        elif result["status"] == "success":
            target["write"] = True
            target["change"] = result["change"]
        elif "APPAP282E" in result["message"] or "change in progress" in result["message"].lower():
            target["status"] = "pending"
            target["message"] = "CyberArk is changing this password; nothing written, the next run retries"
        else:
            target["status"] = "failed"
            target["message"] = "CyberArk: {}".format(result["message"][:300] or "no message")

    writes = [t for t in targets if t.get("write")]
    outputs = {
        "targets_json": json.dumps(targets),
        "has_writes": "yes" if writes else "no",
        "write_count": len(writes),
        "write_assets": [t["asset"] for t in writes],
        "write_fields": [t["pwd_field"] for t in writes],
    }

    # Return a JSON-serializable object
    assert json.dumps(outputs)
    return outputs
