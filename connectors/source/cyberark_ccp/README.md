# CyberArk CCP

Retrieves credentials from a CyberArk Central Credential Provider (CCP) vault over mutual TLS. Used by
UC1 (`soar-playbooks`, `docs/usecases/uc1_implementation_plan.md`) to rotate SOAR asset credentials.

- **Version:** 1.0.30 · **Type:** information · **Python:** 3.13
- **Min SOAR version:** 6.4.1 declared (`min_phantom_version`); built and run against SOAR 8.6 (soar8)
- **Action-only:** no `on_poll`, no ingest label

## Prerequisites

1. The CCP web service reachable over HTTPS from the SOAR host.
2. An **Application ID** registered in CyberArk PVWA and allowed to retrieve the credentials.
3. A **client certificate and private key** (PEM) issued for that Application ID; optionally a CA
   certificate if CCP uses an internal CA.
4. A **test safe and username** that resolve to exactly one vault entry, for Test Connectivity.

## Installation

Build on the connected host, never on the air-gapped target:

```bash
tools/build.sh cyberark_ccp                 # -> dist/cyberark_ccp-v<version>.tgz
tools/install_app.sh dist/cyberark_ccp-v<version>.tgz
```

On a target without the repo, install the `.tgz` through **Apps > Install App**. The REST install takes a
JSON body `{"app": "<base64 of the .tgz>"}`; a multipart upload fails with a UTF-8 decode error. SOAR
refuses an `app_version` at or below the installed one.

## Asset configuration

| Field | Type | Required | Notes |
|---|---|---|---|
| `base_url` | string | yes | CCP base URL, e.g. `https://ccp.corp.local` |
| `app_id` | string | yes | CyberArk Application ID |
| `timeout` | numeric | no | seconds per request, default 60 |
| `verify_ssl` | boolean | no | default true |
| `client_cert` | string | yes | client certificate, full PEM with its BEGIN/END lines |
| `client_key` | password | yes | private key, full PEM (RSA PKCS1, PKCS8 or EC) |
| `client_ca` | string | no | CA certificate PEM, for an internal CA |
| `test_safe` / `test_username` | string | yes | the account Test Connectivity reads |

SOAR's text fields mangle PEM whitespace; the connector re-wraps the PEM and writes it to temp files per
call. Enter the key by hand on a new appliance: a password field does not survive an export, and one
read over REST and written back is corrupted.

## Actions

| Action | Type | What it does |
|---|---|---|
| `test connectivity` | test | Reads `test_safe`/`test_username`: proves mTLS, the AppID and vault access |
| `get secret` | investigate | `GET /AIMWebService/api/Accounts` for one credential |

**`get secret` parameters:** `safe` (required, contains `cyberark safe`), `username` (required,
`user name`), `object` (optional, the vault object name), `address` (optional, `host name`). Use
`object` or `address` when several accounts share a username.

**Outputs** (`action_result.data.*`, CyberArk's PascalCase normalised): `password` (`password`),
`username` (`user name`), `address` (`host name`), `safe` (`cyberark safe`), `object`,
`password_change_in_process`. Summary: `credentials_found`. The `password` value is a real credential:
never log it or write it to an artifact or note.

Retries: up to 3 on HTTP 500/502/503/504 (not 429).

## CyberArk error codes

| Code | Reported as | Fix |
|---|---|---|
| `APPAP004E` | Not Found | check the safe and object names |
| `APPAP005E` | Validation Error | several entries match: add `object` or `address` (also fails Test Connectivity) |
| `APPAP007E` | API Error | check the vault's status |
| `APPAP282E` | API Error | password change in progress: retry later (UC1 rechecks after 5 minutes) |
| `APPAP306E` | Auth Error | check the AppID, the client certificate and CyberArk's IP restrictions |
| `AIMWS030E` | Validation Error | check the parameter syntax |

TLS errors: check that `client_cert` and `client_key` are valid PEM, that `client_ca` holds an internal
CA, and that CCP trusts the client certificate. There is no "list safes" or "list accounts" action: the
safe and username must be known.
