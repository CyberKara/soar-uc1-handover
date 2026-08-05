# CyberArk CCP

## Overview

Retrieve credentials from CyberArk Central Credential Provider (CCP) vault.

- **Version:** 1.0.29
- **Type:** information
- **Auth:** mTLS (mutual TLS with client certificate + key)
- **Python:** 3.13
- **Min SOAR version:** 6.4.1 (declared `min_phantom_version`; actually built/run against SOAR 8.5 in this homelab — soar8)
- **Polling:** No — action-only connector, no event label needed

## Prerequisites

1. CyberArk CCP web service accessible over HTTPS from the SOAR host.
2. An **Application ID** registered in CyberArk PVWA, authorized to retrieve credentials.
3. A **client certificate + private key** issued for the Application ID (PEM format).
4. Optional: custom CA certificate if CCP uses an internal CA.
5. A **test safe** and **test username** that resolve to a single unique vault entry — used for the Test Connectivity button.

## Installation

This is an air-gapped target (soar8) — build on a connected host, transfer the
package, install without ever compiling on the target itself.

Build (from the repo root, on the connected build host):

```bash
tools/build.sh cyberark_ccp
```

Produces `dist/cyberark_ccp-v<version>.tgz`. Transfer that file to the air-gapped
environment (USB, secure file transfer, etc.), then install via **Apps > Install App**
in the SOAR UI, or via REST:

```bash
python3 - <<'PY'
import json, base64, requests
requests.packages.urllib3.disable_warnings()
cfg = json.load(open("config/soar_config.json"))["soar8"]  # or your target env
with open("dist/cyberark_ccp-v<version>.tgz", "rb") as f:
    payload = {"app": base64.b64encode(f.read()).decode()}
r = requests.post(cfg["url"] + "/rest/app", auth=(cfg["user"], cfg["password"]),
                   verify=False, json=payload)
print(r.status_code, r.json())
PY
```

(Multipart `-F` upload fails with a UTF-8 decode error on this SOAR version —
use the base64 JSON body form above.) A version bump (`app_version` in
`cyberark_ccp.json`) above whatever's currently installed is required — SOAR
refuses to install an app whose version isn't strictly greater than the live one.

## Asset Configuration

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `base_url` | string | Yes | CyberArk CCP base URL | `https://ccp.corp.local` |
| `app_id` | string | Yes | CyberArk Application ID | `SOAR_CCP_App` |
| `timeout` | numeric | No | Request timeout in seconds (default: 60) | `60` |
| `verify_ssl` | boolean | No | Verify server TLS certificate (default: true) | `true` |
| `client_cert` | string | Yes | Client certificate PEM string (full PEM including BEGIN/END markers) | `-----BEGIN CERTIFICATE-----...` |
| `client_key` | password | Yes | Client private key PEM string (stored encrypted) | `-----BEGIN PRIVATE KEY-----...` |
| `client_ca` | string | No | Custom CA certificate PEM string (if CCP uses internal CA) | `-----BEGIN CERTIFICATE-----...` |
| `test_safe` | string | Yes | Safe name for connectivity testing only | `TestSafe` |
| `test_username` | string | Yes | Username for connectivity testing only | `svc_test` |

**PEM formatting:** Paste the full PEM content including `-----BEGIN/END-----` markers. The connector automatically normalizes whitespace that SOAR may mangle, for RSA (PKCS1), PKCS8, and EC private keys, plus certificate bundles.

**Test credentials:** `test_safe` + `test_username` must resolve to exactly one vault entry. If multiple entries match, test connectivity will fail with APPAP005E.

## Test Connectivity

Calls CCP with `test_safe` / `test_username` to verify mTLS handshake, AppID authorization, and credential retrieval.

**Expected result:** "Test Connectivity Passed" — confirms mTLS, AppID, and vault access all work.

## Actions

| Action | Identifier | Type | Description |
|--------|-----------|------|-------------|
| test connectivity | `test_connectivity` | test | Validate mTLS + AppID + vault access |
| get secret | `get_secret` | investigate | Retrieve a credential from the vault |

### get secret

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `safe` | string | Yes | CyberArk safe name |
| `username` | string | Yes | Account username to retrieve |
| `object` | string | No | Object name (for disambiguation) |
| `address` | string | No | Filter by address/hostname (for disambiguation) |

**Returns:** `password`, `username`, `address`, `safe`, `object`, `password_change_in_process`

## Troubleshooting

| Error Code | Meaning | Fix |
|------------|---------|-----|
| `APPAP004E` | Object not found | Verify safe and username/object names exist in vault |
| `APPAP005E` | Multiple matches | Add `object` or `address` parameter to disambiguate |
| `APPAP007E` | API error | Check CyberArk Vault status and availability |
| `APPAP282E` | Password change in progress | Retry after a delay — rotation is underway |
| `APPAP306E` | Authentication error | Verify AppID, client certificate, and IP restrictions in CyberArk |

**SSL/TLS errors:** Verify that `client_cert` and `client_key` are valid PEM format. If using an internal CA, paste the CA cert in `client_ca`. Check that the CCP server trusts the client cert.

**No list action:** There is no "list safes" or "list accounts" — you must know the `safe` and `username` in advance.
