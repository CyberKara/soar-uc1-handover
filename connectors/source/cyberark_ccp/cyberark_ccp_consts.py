# cyberark_ccp_consts.py
"""Constants for CyberArk CCP SOAR Connector."""

# API Configuration
DEFAULT_TIMEOUT = 60  # seconds (NFR6)
MAX_RETRIES = 3       # (NFR7)
RETRY_STATUS_CODES = [500, 502, 503, 504]  # NO 429
CCP_API_PATH = "/AIMWebService/api/Accounts"

# Error Message Prefixes
ERR_AUTH = "Auth Error"
ERR_API = "API Error"
ERR_NOT_FOUND = "Not Found"
ERR_VALIDATION = "Validation Error"

# CyberArk Error Code -> (Prefix, User Message)
CYBERARK_ERROR_CODES = {
    "APPAP004E": (ERR_NOT_FOUND, "Verify safe/object names"),
    "APPAP005E": (ERR_VALIDATION, "Add username/address filter"),
    "APPAP007E": (ERR_API, "Check CyberArk Vault status"),
    "APPAP282E": (ERR_API, "Password change in progress, retry later"),
    "APPAP306E": (ERR_AUTH, "Verify AppID and IP/cert config"),
    "AIMWS030E": (ERR_VALIDATION, "Check parameter syntax"),
}

# Response Field Normalization: CyberArk PascalCase -> snake_case
RESPONSE_FIELD_MAP = {
    "Content": "password",
    "UserName": "username",
    "Address": "address",
    "Safe": "safe",
    "Name": "object",
    "PasswordChangeInProcess": "password_change_in_process",
}
