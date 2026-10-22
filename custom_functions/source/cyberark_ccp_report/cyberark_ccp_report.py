def cyberark_ccp_report(targets_json=None, container_id=None, list_name=None, **kwargs):
    """
    Write the refresh result to the list, one note and the container severity.
    
    Args:
        targets_json: targets_json of the last cyberark_ccp_* function that ran.
        container_id (CEF type: phantom container id): Container to write the note and the severity on.
        list_name: Custom list name (default: cyberark_ccp_rotation_state).
    
    Returns a JSON-serializable object that implements the configured data paths:
        summary: One line: the number of targets per status.
        severity: Severity set on the container: high, medium or low.
    """
    ############################ Custom Code Goes Below This Line #################################
    import json
    import re
    from datetime import datetime
    import phantom.rules as phantom

    note_title = "Credential Refresh"
    # The airgapped appliance cuts a note at about 22,000 characters
    note_cap = 19000
    table_header = ["| Asset | Status | Message |", "|---|---|---|"]
    state_header = ["asset", "safe", "user_field", "pwd_field", "address",
                    "connector", "username", "status", "message", "last_rotated", "event_link"]
    list_name = list_name or "cyberark_ccp_rotation_state"
    container_id = int(container_id[0] if isinstance(container_id, (list, tuple)) else container_id)

    def md(value):
        text = " ".join(str(value if value is not None else "").split())
        return re.sub(r"([\\`*_\[\]<>|#])", r"\\\1", text)

    targets = json.loads(targets_json or "[]")

    # The connectivity tests started by cyberark_ccp_start_tests.
    for target in targets:
        if not target.get("test_run"):
            continue
        run = phantom.requests.get(uri=phantom.build_phantom_rest_url("action_run", target["test_run"]), verify=False).json()
        if run.get("status") == "success":
            target["status"], target["message"] = "success", "Written; test connectivity passed"
        elif run.get("status") == "failed":
            # The app run holds the connector's own reason; the action run only
            # says "1 action failed".
            reason = run.get("message") or "no message"
            app_runs = phantom.requests.get(
                uri=phantom.build_phantom_rest_url("app_run"),
                params={"_filter_action_run": target["test_run"]},
                verify=False,
            ).json().get("data", [])
            if app_runs and app_runs[0].get("message"):
                reason = app_runs[0]["message"].split("Message: ", 1)[-1].strip('"')
            target["status"] = "written (test failed)"
            target["message"] = "Test connectivity failed: {}".format(reason[:300])
        else:
            target["status"] = "written (no test result)"
            target["message"] = "Test connectivity still {} after the wait".format(run.get("status") or "unknown")
    for target in targets:
        if target.get("written") and target.get("change"):
            target["status"] = "written (change pending)"
            target["message"] += "; CyberArk was changing this password, the next run writes the new one"

    # Columns 6-11 of each target's row; the operator's columns and row order are kept.
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    event_link = "{}/mission/{}".format(phantom.get_base_url() or "", container_id)
    by_asset = {t["asset"]: t for t in targets}
    list_note = ""
    read_success, read_message, rows = phantom.get_list(list_name=list_name)
    if read_success:
        content = [state_header]
        for row in rows or []:
            if not row or row[0] == "asset":
                continue
            row = (list(row) + [""] * len(state_header))[:len(state_header)]
            target = by_asset.get((row[0] or "").strip())
            if target:
                row[5:] = [target["connector"], target["username"], target["status"],
                           target["message"][:200], now, event_link]
            content.append(row)
        phantom.set_list(list_name=list_name, values=content)
    else:
        list_note = "List `{}` not updated: {}".format(list_name, read_message)

    counts = {}
    for target in targets:
        counts[target["status"]] = counts.get(target["status"], 0) + 1
    statuses = set(counts)
    if statuses & {"failed", "written (test failed)"}:
        severity = "high"
    elif statuses & {"pending", "written (change pending)", "written (no test result)"}:
        severity = "medium"
    else:
        severity = "low"

    if targets:
        summary = "{} target(s): ".format(len(targets)) + ", ".join(
            "{} {}".format(count, status) for status, count in sorted(counts.items()))
    else:
        summary = "No target: the list `{}` has no row".format(list_name)

    lines = [("**Result:** {}".format(summary), False)]
    if list_note:
        lines.append((list_note, False))
    if targets:
        lines.append(("", False))
        lines += [(line, True) for line in table_header]
        lines += [("| {} | {} | {} |".format(md(t["asset"]), md(t["status"]), md(t["message"])), True) for t in targets]

    # Notes over note_cap are split into "Title (k/N)", repeating the table header.
    parts, current = [], []
    for text, in_table in lines:
        if current and sum(len(line) + 1 for line in current) + len(text) + 1 > note_cap:
            parts.append("\n".join(current))
            current = list(table_header) if in_table else []
        current.append(text)
    if current:
        parts.append("\n".join(current))

    title = "{} - {}".format(note_title, datetime.now().strftime("%Y-%m-%d %H:%M"))
    for index, body in enumerate(parts, start=1):
        success, message, _note_id = phantom.add_note(
            container=container_id,
            note_type="general",
            title=title if len(parts) == 1 else "{} ({}/{})".format(title, index, len(parts)),
            content=body,
            note_format="markdown",
        )
        if not success:
            raise RuntimeError("Note not written: {}".format(message))

    response = phantom.requests.post(
        uri=phantom.build_phantom_rest_url("container", container_id),
        data=json.dumps({"severity": severity}),
        verify=False,
    )
    if response.status_code != 200:
        raise RuntimeError("Severity not set: HTTP {}".format(response.status_code))

    outputs = {"summary": summary, "severity": severity}
    phantom.debug("Credential refresh: {} (severity {})".format(summary, severity))

    # Return a JSON-serializable object
    assert json.dumps(outputs)
    return outputs
