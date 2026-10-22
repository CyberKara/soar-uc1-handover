def cyberark_ccp_get_targets(list_name=None, **kwargs):
    """
    Read the CyberArk refresh targets from the list cyberark_ccp_rotation_state and the CyberArk accounts to query.
    
    Args:
        list_name: Custom list name (default: cyberark_ccp_rotation_state).
    
    Returns a JSON-serializable object that implements the configured data paths:
        targets_json: JSON: one dict per list row: asset, asset_id, app_id, connector, safe, username, user_field, pwd_field, address, status, message; status 'failed' when the row cannot be used.
        has_queries: yes when at least one account is to be queried, else no.
        query_count: Number of CyberArk accounts to query.
        total_count: Number of targets (list rows).
        safes: Safe of each account to query (parallel to usernames, addresses).
        usernames: Username of each account to query.
        addresses: Address filter of each account to query; empty when not set.
    """
    ############################ Custom Code Goes Below This Line #################################
    import json
    import phantom.rules as phantom

    # One target per list row, so a row that cannot be refreshed is reported,
    # not skipped: its status is "failed" and it gets no CyberArk query.
    list_name = list_name or "cyberark_ccp_rotation_state"
    targets = []

    def target(row=None, error=None):
        cells = [(str(cell).strip() if cell is not None else "") for cell in (row or [])] + [""] * 5
        return {
            "asset": cells[0] or "(list)", "asset_id": None, "app_id": None, "connector": "",
            "safe": cells[1], "username": "", "user_field": cells[2], "pwd_field": cells[3],
            "address": cells[4], "status": "failed" if error else None, "message": error or "",
        }

    read_success, read_msg, rows = phantom.get_list(list_name=list_name)
    if not read_success:
        targets.append(target(error="Cannot read list '{}': {}".format(list_name, read_msg)))
        rows = []

    # phantom.requests carries SOAR session auth — do not replace with system requests
    for row in rows or []:
        if not row or not any(row) or row[0] == "asset":
            continue  # header or empty row
        entry = target(row)
        targets.append(entry)
        if not (entry["asset"] and entry["safe"] and entry["user_field"] and entry["pwd_field"]):
            entry["status"] = "failed"
            entry["message"] = "Row incomplete: asset, safe, user_field and pwd_field are required"
            continue

        # pretty adds _pretty_app, the app's name: the Automation role cannot read /rest/app
        response = phantom.requests.get(
            uri=phantom.build_phantom_rest_url("asset"),
            params={"_filter_name": "\"{}\"".format(entry["asset"]), "pretty": ""},
            verify=False,
        )
        if response.status_code != 200:
            entry["status"] = "failed"
            entry["message"] = "Asset lookup failed: HTTP {}".format(response.status_code)
            continue
        matches = response.json().get("data", [])
        if len(matches) != 1:
            entry["status"] = "failed"
            entry["message"] = "Asset not found" if not matches else "Several assets have this name"
            continue

        asset = matches[0]
        entry["asset_id"] = asset.get("id")
        entry["app_id"] = asset.get("app")
        entry["connector"] = asset.get("_pretty_app") or ""
        entry["username"] = (asset.get("configuration") or {}).get(entry["user_field"]) or ""
        if not entry["username"]:
            entry["status"] = "failed"
            entry["message"] = "Asset field '{}' is empty".format(entry["user_field"])

    # One CyberArk query per account, even when several assets share it.
    accounts = []
    for entry in targets:
        account = (entry["safe"], entry["username"], entry["address"])
        if not entry["status"] and account not in accounts:
            accounts.append(account)

    outputs = {
        "targets_json": json.dumps(targets),
        "has_queries": "yes" if accounts else "no",
        "query_count": len(accounts),
        "total_count": len(targets),
        "safes": [a[0] for a in accounts],
        "usernames": [a[1] for a in accounts],
        "addresses": [a[2] for a in accounts],
    }
    phantom.debug("{} target(s), {} CyberArk account(s) to query".format(len(targets), len(accounts)))

    # Return a JSON-serializable object
    assert json.dumps(outputs)
    return outputs
