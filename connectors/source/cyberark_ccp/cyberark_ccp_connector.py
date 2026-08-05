# cyberark_ccp_connector.py
"""CyberArk CCP SOAR Connector - Classic BaseConnector for SOAR 6.4.1."""

import json
import os
import tempfile

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import phantom.app as phantom
from phantom.action_result import ActionResult
from phantom.base_connector import BaseConnector

from cyberark_ccp_consts import (
    CCP_API_PATH,
    CYBERARK_ERROR_CODES,
    DEFAULT_TIMEOUT,
    MAX_RETRIES,
    RESPONSE_FIELD_MAP,
    RETRY_STATUS_CODES,
)


class CyberArkCcpConnector(BaseConnector):
    """CyberArk Central Credential Provider connector for Splunk SOAR."""

    def __init__(self):
        super(CyberArkCcpConnector, self).__init__()
        self._state = None
        self._session = None
        self._base_url = None

    def initialize(self):
        """Called once per action execution. Load state, set up session with retry."""
        self._state = self.load_state()
        if not isinstance(self._state, dict):
            self.debug_print("Resetting corrupted state file")
            self._state = {"app_version": self.get_app_json().get("app_version")}

        config = self.get_config()
        self._base_url = config.get('base_url', '').strip('/')

        self._session = requests.Session()
        retry = Retry(
            total=MAX_RETRIES,
            status_forcelist=RETRY_STATUS_CODES,
            backoff_factor=1,
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        return phantom.APP_SUCCESS

    def finalize(self):
        """Cleanup session and save state."""
        if self._session:
            self._session.close()
        self.save_state(self._state)
        return phantom.APP_SUCCESS

    def handle_action(self, param):
        """Dispatch to action handler based on action identifier."""
        action_id = self.get_action_identifier()
        self.debug_print("action_id", action_id)

        action_mapping = {
            'test_connectivity': self._handle_test_connectivity,
            'get_secret': self._handle_get_secret,
        }

        action = action_mapping.get(action_id)
        if action:
            return action(param)

        return phantom.APP_ERROR

    def handle_exception(self, exception):
        """Handle unrecoverable exceptions."""
        self.set_status(
            phantom.APP_ERROR,
            "Unhandled exception: {}".format(
                self._get_error_message_from_exception(exception)
            )
        )
        return phantom.APP_ERROR

    # ---- Action Handlers ----

    def _handle_test_connectivity(self, param):
        """Validate CyberArk CCP connectivity using mTLS + AppID."""
        action_result = self.add_action_result(ActionResult(dict(param)))
        self.save_progress("DEBUG GUI: Starting test connectivity action")

        config = self.get_config()
        api_params = {
            'Safe': config['test_safe'],
            'UserName': config['test_username'],
        }

        ret_val, response = self._make_rest_call(api_params, action_result)

        if phantom.is_fail(ret_val):
            self.save_progress("Test Connectivity Failed")
            return action_result.get_status()

        self.save_progress("Test Connectivity Passed")
        return action_result.set_status(phantom.APP_SUCCESS, "Connectivity test passed")

    def _handle_get_secret(self, param):
        """Retrieve credential from CyberArk CCP vault."""
        action_result = self.add_action_result(ActionResult(dict(param)))
        self.save_progress("DEBUG GUI: Starting get secret action")

        api_params = {
            'Safe': param['safe'],
            'UserName': param['username'],
        }

        object_name = param.get('object', '')
        if object_name:
            api_params['Object'] = object_name
        address = param.get('address', '')
        if address:
            api_params['Address'] = address

        ret_val, response = self._make_rest_call(api_params, action_result)

        if phantom.is_fail(ret_val):
            return action_result.get_status()

        normalized = {}
        for cyberark_key, snake_key in RESPONSE_FIELD_MAP.items():
            if cyberark_key in response:
                normalized[snake_key] = response[cyberark_key]

        action_result.add_data(normalized)
        summary = action_result.update_summary({})
        summary['credentials_found'] = 1

        return action_result.set_status(phantom.APP_SUCCESS, "Successfully retrieved credential")

    # ---- REST Call Wrapper ----

    def _make_rest_call(self, api_params, action_result):
        """Execute a CCP API call with mTLS cert setup and cleanup.

        Returns:
            tuple: (status, response_data) - RetVal pattern
        """
        config = self.get_config()
        app_id = config['app_id']
        timeout = config.get('timeout', DEFAULT_TIMEOUT)

        url = "{}{}".format(self._base_url, CCP_API_PATH)
        api_params['AppID'] = app_id

        self.save_progress("DEBUG GUI: GET {}".format(url))

        cert_path = key_path = ca_path = None
        try:
            cert_path, key_path, ca_path = self._setup_cert_files()
            self.save_progress("DEBUG GUI: Cert files created")

            verify_ssl = config.get('verify_ssl', True)
            verify = ca_path if (verify_ssl and ca_path) else verify_ssl
            response = self._session.get(
                url, params=api_params, timeout=timeout,
                cert=(cert_path, key_path), verify=verify
            )

            self.save_progress("DEBUG GUI: HTTP {} received".format(response.status_code))

            return self._process_response(response, action_result)

        except requests.exceptions.SSLError as e:
            self.save_progress("DEBUG GUI: SSL error")
            return (
                action_result.set_status(
                    phantom.APP_ERROR,
                    "SSL error during connection: {}".format(str(e))
                ),
                None
            )
        except requests.ConnectionError:
            self.save_progress("DEBUG GUI: Connection error")
            return (
                action_result.set_status(
                    phantom.APP_ERROR,
                    "Unable to connect to CyberArk CCP"
                ),
                None
            )
        except requests.Timeout:
            self.save_progress("DEBUG GUI: Request timed out")
            return (
                action_result.set_status(
                    phantom.APP_ERROR,
                    "Request timed out after {} seconds".format(timeout)
                ),
                None
            )
        except Exception as e:
            self.save_progress("DEBUG GUI: Unexpected error")
            return (
                action_result.set_status(
                    phantom.APP_ERROR,
                    self._get_error_message_from_exception(e)
                ),
                None
            )
        finally:
            self._cleanup_temp_files(cert_path, key_path, ca_path)
            self.save_progress("DEBUG GUI: Cert files cleaned up")

    def _redact_response_text(self, text):
        """Redact secret fields from CCP response text before logging.

        Why: CCP's Accounts endpoint always returns JSON on success; any non-JSON
        body is an error page, and we prefer to drop it entirely rather than risk
        logging a secret that a misbehaving server might echo in HTML/text form.
        """
        if not text:
            return text
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return "**NON-JSON RESPONSE REDACTED**"
        if isinstance(data, dict) and "Content" in data:
            data["Content"] = "**REDACTED**"
            return json.dumps(data)
        return text

    def _process_response(self, response, action_result):
        """Process HTTP response and return (status, data)."""
        action_result.add_debug_data({
            'r_status_code': response.status_code,
            'r_text': self._redact_response_text(response.text),
            'r_headers': dict(response.headers),
        })

        content_type = response.headers.get('Content-Type', '')

        if 'json' in content_type:
            return self._process_json_response(response, action_result)

        if 'html' in content_type:
            return (
                action_result.set_status(
                    phantom.APP_ERROR,
                    "Unexpected HTML response. Status: {}".format(response.status_code)
                ),
                None
            )

        if not response.text:
            if 200 <= response.status_code < 399:
                return (phantom.APP_SUCCESS, {})
            return (
                action_result.set_status(
                    phantom.APP_ERROR,
                    "Empty response. Status: {}".format(response.status_code)
                ),
                None
            )

        if 200 <= response.status_code < 399:
            return (phantom.APP_SUCCESS, response.text)

        return (
            action_result.set_status(
                phantom.APP_ERROR,
                "Error from server. Status: {}. Response: {}".format(
                    response.status_code, self._redact_response_text(response.text)[:500]
                )
            ),
            None
        )

    def _process_json_response(self, response, action_result):
        """Parse JSON response and handle CyberArk error codes."""
        try:
            resp_json = response.json()
        except Exception as e:
            return (
                action_result.set_status(
                    phantom.APP_ERROR,
                    "Unable to parse JSON response. Error: {}".format(str(e))
                ),
                None
            )

        if 200 <= response.status_code < 399:
            return (phantom.APP_SUCCESS, resp_json)

        error_code = resp_json.get('ErrorCode', '')
        if error_code in CYBERARK_ERROR_CODES:
            prefix, message = CYBERARK_ERROR_CODES[error_code]
            self.save_progress("DEBUG GUI: CyberArk error {}: {}".format(error_code, message))
            return (
                action_result.set_status(
                    phantom.APP_ERROR,
                    "{}: {}".format(prefix, message)
                ),
                None
            )

        error_msg = resp_json.get('ErrorMsg', resp_json.get('message', 'Unknown error'))
        return (
            action_result.set_status(
                phantom.APP_ERROR,
                "Error from server. Status: {}. Message: {}".format(
                    response.status_code, error_msg
                )
            ),
            None
        )

    # ---- Cert Handling ----

    def _normalize_pem(self, pem_string):
        """Normalize PEM for CERT, PRIVATE KEY, and multi-CERT bundles."""
        if not pem_string:
            return pem_string

        pem_string = pem_string.strip()
        normalized_blocks = []

        block_types = [
            ("-----BEGIN CERTIFICATE-----", "-----END CERTIFICATE-----"),
            ("-----BEGIN PRIVATE KEY-----", "-----END PRIVATE KEY-----"),
            ("-----BEGIN RSA PRIVATE KEY-----", "-----END RSA PRIVATE KEY-----"),
            ("-----BEGIN EC PRIVATE KEY-----", "-----END EC PRIVATE KEY-----"),
        ]

        for header, footer in block_types:
            parts = pem_string.split(header)
            for part in parts:
                if footer in part:
                    body, _ = part.split(footer, 1)
                    body = "".join(body.split())
                    lines = []
                    while body:
                        lines.append(body[:64])
                        body = body[64:]
                    block = header + "\n" + "\n".join(lines) + "\n" + footer
                    normalized_blocks.append(block)

        if not normalized_blocks:
            return pem_string

        return "\n".join(normalized_blocks)

    def _setup_cert_files(self):
        """Normalize PEM and write to temp files, return (cert_path, key_path, ca_path)."""
        config = self.get_config()
        cert_pem = config.get('client_cert', '')
        key_pem = config.get('client_key', '')

        if not cert_pem or not key_pem:
            raise ValueError("client_cert and client_key are required for mTLS")

        cert_pem = self._normalize_pem(cert_pem)
        key_pem = self._normalize_pem(key_pem)
        ca_pem = config.get('client_ca', '')
        if ca_pem:
            ca_pem = self._normalize_pem(ca_pem)

        written_paths = []
        try:
            cert_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem', mode='w')
            written_paths.append(cert_file.name)
            cert_file.write(cert_pem)
            cert_file.close()

            key_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem', mode='w')
            written_paths.append(key_file.name)
            key_file.write(key_pem)
            key_file.close()

            ca_path = None
            if ca_pem:
                ca_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pem', mode='w')
                written_paths.append(ca_file.name)
                ca_file.write(ca_pem)
                ca_file.close()
                ca_path = ca_file.name
        except Exception:
            self._cleanup_temp_files(*written_paths)
            raise

        return cert_file.name, key_file.name, ca_path

    def _cleanup_temp_files(self, *file_paths):
        """Safely remove temp cert files."""
        for path in file_paths:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    # ---- Utility ----

    def _get_error_message_from_exception(self, e):
        """Extract error message string from exception safely."""
        error_code = None
        error_message = "Error message unavailable"
        try:
            if hasattr(e, 'args') and e.args:
                if len(e.args) > 1:
                    error_code = e.args[0]
                    error_message = e.args[1]
                elif len(e.args) == 1:
                    error_message = e.args[0]
        except Exception:
            pass

        if not error_code:
            return "Error Message: {}".format(error_message)
        return "Error Code: {}. Error Message: {}".format(error_code, error_message)


# ---- Entry Point ----

def main():
    import argparse
    import json

    argparser = argparse.ArgumentParser()
    argparser.add_argument('input_test_json', help='Input Test JSON file')
    args = argparser.parse_args()

    with open(args.input_test_json) as f:
        in_json = f.read()
        in_json = json.loads(in_json)
        print(json.dumps(in_json, indent=4))

        connector = CyberArkCcpConnector()
        connector.print_progress_message = True
        result = connector._handle_action(json.dumps(in_json), None)
        print(json.dumps(json.loads(result), indent=4))

    exit(0)


if __name__ == '__main__':
    main()
