def cyberark_ccp_update_asset(asset=None, configuration_updates=None, **kwargs):
    """
    Update one or more asset configuration fields; every other field is kept.
    
    Args:
        asset: Asset numeric ID or asset name.
        configuration_updates: JSON string of configuration fields to update.
    
    Returns a JSON-serializable object that implements the configured data paths:
        success: Whether the update succeeded (true/false).
        asset_id (CEF type: phantom asset id): The numeric asset ID that was updated.
        asset_name: The asset name.
        updated_fields: List of field names that were updated.
        message: Status message.
    """
    ############################ Custom Code Goes Below This Line #################################
    import json
    import phantom.rules as phantom

    # phantom.requests carries SOAR session auth — do not replace with system requests

    outputs = {
        "success": False,
        "asset_id": None,
        "asset_name": None,
        "updated_fields": [],
        "message": ""
    }

    # Validate inputs
    if asset is None:
        raise ValueError("asset parameter is required (numeric ID or name)")

    if configuration_updates is None:
        raise ValueError("configuration_updates parameter is required (JSON string)")

    # Parse configuration_updates if string
    if isinstance(configuration_updates, str):
        try:
            updates = json.loads(configuration_updates)
        except json.JSONDecodeError as e:
            raise ValueError("configuration_updates must be valid JSON: {}".format(str(e)))
    elif isinstance(configuration_updates, dict):
        updates = configuration_updates
    else:
        raise TypeError("configuration_updates must be a JSON string or dict")

    if not updates:
        raise ValueError("configuration_updates cannot be empty")

    # Resolve asset ID
    url = phantom.build_phantom_rest_url("asset")

    if isinstance(asset, int):
        asset_url = "{}/{}".format(url, asset)
    elif isinstance(asset, str):
        # Try name lookup first — callers always pass names, never bare IDs
        params = {"_filter_name": "\"{}\"".format(asset)}
        response = phantom.requests.get(uri=url, params=params, verify=False).json()
        if response.get("count", 0) == 1:
            asset_url = "{}/{}".format(url, response["data"][0]["id"])
        elif response.get("count", 0) > 1:
            raise RuntimeError("Multiple assets found with name: {}".format(asset))
        elif asset.isdigit():
            asset_url = "{}/{}".format(url, asset)
        else:
            raise RuntimeError("Asset not found: {}".format(asset))
    else:
        raise TypeError("asset must be a numeric ID or string name")

    # Read the asset for its id, name, tags and description only
    current = phantom.requests.get(uri=asset_url, verify=False).json()

    if not current.get("id"):
        raise RuntimeError("Failed to read asset: {}".format(asset))

    asset_id = current["id"]
    asset_name = current.get("name", "")
    updated_fields = list(updates)
    # Echoed on failure too: a caller matches results to its assets by name
    outputs["asset_id"] = asset_id
    outputs["asset_name"] = asset_name

    # Send only the updated keys: SOAR keeps every configuration key the POST
    # leaves out. GET returns each password field as "********", and posting
    # that back would store "********" as the password.
    payload = {
        "configuration": updates,
        "tags": current.get("tags", []),
        "name": asset_name,
        "description": current.get("description", ""),
    }
    response = phantom.requests.post(uri=asset_url, data=json.dumps(payload), verify=False).json()

    if response.get("success"):
        outputs["success"] = True
        outputs["updated_fields"] = updated_fields
        outputs["message"] = "Successfully updated {} field(s): {}".format(
            len(updated_fields), ", ".join(updated_fields)
        )
    else:
        outputs["message"] = "Update failed: {}".format(
            response.get("message", "Unknown error")
        )

    # Return a JSON-serializable object
    assert json.dumps(outputs)
    return outputs
