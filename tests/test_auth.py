from __future__ import annotations

import base64
import json
import sys
import time
import types
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

BASE_PATH = Path(__file__).parents[1] / "custom_components/codex_usage"

aiohttp_stub = types.ModuleType("aiohttp")


class ClientTimeout:
    def __init__(self, total: int) -> None:
        self.total = total


aiohttp_stub.ClientTimeout = ClientTimeout
aiohttp_stub.ClientError = Exception
aiohttp_stub.ClientSession = object
sys.modules.setdefault("aiohttp", aiohttp_stub)

root_package = types.ModuleType("custom_components")
root_package.__path__ = [str(BASE_PATH.parent)]
sys.modules.setdefault("custom_components", root_package)

package = types.ModuleType("custom_components.codex_usage")
package.__path__ = [str(BASE_PATH)]
sys.modules.setdefault("custom_components.codex_usage", package)

for name in ("const", "auth"):
    spec = spec_from_file_location(
        f"custom_components.codex_usage.{name}", BASE_PATH / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

auth = sys.modules["custom_components.codex_usage.auth"]


def jwt(payload: dict[str, object]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    return f"header.{encoded.decode()}.signature"


class AuthTest(unittest.TestCase):
    def test_token_config_data_extracts_safe_metadata(self) -> None:
        expires_at = int(time.time()) + 600
        tokens = auth.CodexTokens(
            access_token=jwt({"exp": expires_at}),
            refresh_token="refresh-token",
            id_token=jwt(
                {
                    "https://api.openai.com/profile": {"email": "user@example.com"},
                    "https://api.openai.com/auth": {"chatgpt_account_id": "account-123"},
                }
            ),
        )

        data = auth.token_config_data(tokens)

        self.assertEqual(data["access_token"], tokens.access_token)
        self.assertEqual(data["refresh_token"], "refresh-token")
        self.assertEqual(data["account_email"], "user@example.com")
        self.assertEqual(data["account_id"], "account-123")
        self.assertEqual(data["expires_at"], expires_at)

    def test_needs_refresh_uses_expiry_margin(self) -> None:
        soon = {"access_token": jwt({"exp": int(time.time()) + 60})}
        later = {"access_token": jwt({"exp": int(time.time()) + 900})}

        self.assertTrue(auth.needs_refresh(soon))
        self.assertFalse(auth.needs_refresh(later))

    def test_malformed_jwt_payload_is_empty(self) -> None:
        self.assertEqual(auth.jwt_payload("not-a-token"), {})


if __name__ == "__main__":
    unittest.main()
