def cyberark_asset_get_tagged_for_rotation(list_name=None, **kwargs):
    """
    Discover CyberArk rotation targets from the cyberark_ccp_rotation_state list.
    
    Args:
        list_name: Custom list name (default: cyberark_ccp_rotation_state).
    
    Returns a JSON-serializable object that implements the configured data paths:
        asset_name: Target asset name.
        asset_id (CEF type: phantom asset id): Target asset numeric ID.
        safe: CyberArk safe name from the state list.
        username: Actual username value read from the asset config.
        user_field: Config field name that holds the username.
        pwd_field: Config field name for the password.
        address: CyberArk address filter for disambiguating accounts with the same username.
        app_name: Connector/app name for the target asset.
        total_count: Total number of discovered rotation targets.
    """
    ############################ Custom Code Goes Below This Line #################################
    import json
    import phantom.rules as phantom

    outputs = []
    list_name = list_name or "cyberark_ccp_rotation_state"

    # phantom.requests carries SOAR session auth — do not replace with system requests

    read_success, read_msg, rows = phantom.get_list(list_name=list_name)
    if not read_success:
        phantom.debug("Failed to read list '{}': {}".format(list_name, read_msg))
        rows = []

    for row in (rows or []):
        if not row or len(row) < 4 or row[0] == "asset":
            continue  # skip header row / malformed row

        asset_name = (row[0] or "").strip()
        safe = (row[1] or "").strip()
        user_field = (row[2] or "").strip()
        pwd_field = (row[3] or "").strip()
        address = (row[4].strip() if len(row) > 4 and row[4] else "")

        if not asset_name or not safe or not user_field or not pwd_field:
            phantom.debug("Skipping state list row - incomplete vault mapping: {}".format(row))
            continue

        # Look up asset by name; skip defensively if stale/renamed/deleted
        try:
            url = phantom.build_phantom_rest_url("asset")
            resp = phantom.requests.get(
                uri=url, params={"_filter_name": "\"{}\"".format(asset_name)}, verify=False
            ).json()
        except Exception as e:
            phantom.debug("Failed to look up asset '{}': {}".format(asset_name, e))
            continue

        matches = resp.get("data", [])
        if not matches:
            phantom.debug("Skipping mapping for '{}' - asset not found (stale list row?)".format(asset_name))
            continue
        if len(matches) > 1:
            phantom.debug("Skipping mapping for '{}' - multiple assets matched".format(asset_name))
            continue

        asset = matches[0]

        # `or {}` handles configuration: null explicitly present, not just absent
        config = asset.get("configuration") or {}
        username = config.get(user_field, "")

        if not username:
            phantom.debug("Warning: asset '{}' has empty '{}' config field".format(asset_name, user_field))

        # Resolve app/connector name
        app_name = ""
        app_id = asset.get("product_vendor_id") or asset.get("app")
        if app_id:
            try:
                app_url = phantom.build_phantom_rest_url("app", app_id)
                app_resp = phantom.requests.get(uri=app_url, verify=False).json()
                app_name = app_resp.get("name", "")
            except Exception as e:
                phantom.debug("Warning: failed to resolve app_name for asset '{}' (app_id={}): {}".format(
                    asset_name, app_id, e))

        outputs.append({
            "asset_name": asset.get("name", asset_name),
            "asset_id": asset.get("id"),
            "safe": safe,
            "username": username,
            "user_field": user_field,
            "pwd_field": pwd_field,
            "address": address,
            "app_name": app_name,
            "total_count": 0
        })

    # Set total count on all results
    for item in outputs:
        item["total_count"] = len(outputs)

    phantom.debug("Found {} assets tagged for rotation (list '{}')".format(len(outputs), list_name))

    # Empty list marks the CF as failed on SOAR — return a total_count=0 sentinel instead
    if not outputs:
        outputs = [{
            "asset_name": None, "asset_id": None, "safe": None,
            "username": None, "user_field": None,
            "pwd_field": None, "address": None, "app_name": None,
            "total_count": 0
        }]

    assert json.dumps(outputs)
    return outputs
