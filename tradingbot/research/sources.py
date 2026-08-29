"""Chain data sources.

Everything here is public, read-only chain data. The Etherscan V2 API covers many
chains behind one key, so `chain` is a parameter rather than a separate client.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone

log = logging.getLogger(__name__)

API_KEY_ENV = "ETHERSCAN_API_KEY"

#: Chains reachable through the Etherscan V2 multichain endpoint.
CHAINS: dict[str, dict] = {
    "ethereum": {"id": 1, "explorer": "https://etherscan.io", "symbol": "ETH"},
    "bsc": {"id": 56, "explorer": "https://bscscan.com", "symbol": "BNB"},
    "polygon": {"id": 137, "explorer": "https://polygonscan.com", "symbol": "POL"},
    "base": {"id": 8453, "explorer": "https://basescan.org", "symbol": "ETH"},
    "arbitrum": {"id": 42161, "explorer": "https://arbiscan.io", "symbol": "ETH"},
    "optimism": {"id": 10, "explorer": "https://optimistic.etherscan.io", "symbol": "ETH"},
    "avalanche": {"id": 43114, "explorer": "https://snowscan.xyz", "symbol": "AVAX"},
}

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
# Function selectors read via eth_call.
SELECTORS = {
    "owner": "0x8da5cb5b",
    "getOwner": "0x893d20e8",
    "name": "0x06fdde03",
    "symbol": "0x95d89b41",
    "decimals": "0x313ce567",
    "totalSupply": "0x18160ddd",
}


class SourceError(Exception):
    """The data source could not answer. Never raised for 'no such contract'."""


class AuthError(SourceError):
    """The API key is missing or rejected — fatal and fixable, so never swallowed."""


def is_address(value: str) -> bool:
    """True for a syntactically valid EVM address."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value.startswith("0x") or len(value) != 42:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def normalise_chain(name: str) -> str:
    key = (name or "ethereum").strip().lower()
    aliases = {"eth": "ethereum", "mainnet": "ethereum", "bnb": "bsc",
               "binance": "bsc", "matic": "polygon", "arb": "arbitrum",
               "op": "optimism", "avax": "avalanche"}
    key = aliases.get(key, key)
    if key not in CHAINS:
        raise SourceError(f"unsupported chain {name!r}; known: {', '.join(sorted(CHAINS))}")
    return key


class ChainSource(ABC):
    """Read-only access to one chain's public data."""

    @abstractmethod
    def source_code(self, address: str) -> dict: ...

    @abstractmethod
    def creation(self, address: str) -> dict: ...

    @abstractmethod
    def deployments_by(self, address: str, limit: int = 25) -> tuple[list[dict], bool]: ...

    @abstractmethod
    def call(self, address: str, selector: str) -> str | None: ...

    @abstractmethod
    def first_activity(self, address: str) -> tuple[datetime | None, str | None]: ...


class EtherscanSource(ChainSource):
    """Etherscan V2 multichain API.

    Needs a free API key in $ETHERSCAN_API_KEY. One key covers every chain in
    CHAINS. Requests are paced to stay inside the free tier's rate limit.
    """

    BASE_URL = "https://api.etherscan.io/v2/api"

    def __init__(
        self,
        chain: str = "ethereum",
        api_key: str | None = None,
        timeout: float = 20.0,
        min_interval: float = 0.25,
    ) -> None:
        self.chain = normalise_chain(chain)
        self.chain_id = CHAINS[self.chain]["id"]
        self.explorer = CHAINS[self.chain]["explorer"]
        self.api_key = api_key or os.environ.get(API_KEY_ENV, "")
        self.timeout = timeout
        self.min_interval = min_interval
        self._last_call = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    def _get(self, **params) -> object:
        if not self.api_key:
            raise AuthError(
                f"a free Etherscan API key is required; set ${API_KEY_ENV} "
                f"(get one at https://etherscan.io/apis)"
            )

        # Space out requests so the free tier's rate limit is not tripped.
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        query = urllib.parse.urlencode(
            {"chainid": self.chain_id, "apikey": self.api_key, **params}
        )
        url = f"{self.BASE_URL}?{query}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise SourceError(f"explorer returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SourceError(f"could not reach the explorer: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SourceError("explorer returned a malformed response") from exc
        finally:
            self._last_call = time.monotonic()

        if isinstance(payload, dict) and payload.get("status") == "0":
            message = str(payload.get("message", ""))
            result = str(payload.get("result", ""))
            # "No records found" is a legitimate empty answer, not a failure.
            if "No transactions found" in result or "No records found" in message:
                return []
            if "Invalid API Key" in result or "Missing" in result:
                raise AuthError(
                    f"the explorer rejected the API key ({result}). Check "
                    f"$ETHERSCAN_API_KEY, or get a free key at https://etherscan.io/apis"
                )
            if "rate limit" in result.lower():
                raise SourceError("explorer rate limit reached; wait a moment and retry")
            log.debug("explorer reported: %s / %s", message, result)
            return []

        if isinstance(payload, dict) and "error" in payload:
            raise SourceError(str(payload["error"].get("message", payload["error"])))
        return payload.get("result") if isinstance(payload, dict) else payload

    # ------------------------------------------------------------------
    def source_code(self, address: str) -> dict:
        result = self._get(module="contract", action="getsourcecode", address=address)
        if isinstance(result, list) and result:
            return result[0]
        return {}

    def creation(self, address: str) -> dict:
        result = self._get(
            module="contract", action="getcontractcreation", contractaddresses=address
        )
        if isinstance(result, list) and result:
            return result[0]
        return {}

    def deployments_by(self, address: str, limit: int = 25) -> tuple[list[dict], bool]:
        """Contracts this address has deployed, newest first.

        Returns (deployments, truncated). `truncated` is True when the address has
        more history than one page covers, so the list is a sample, not a census.
        """
        page_size = 10_000
        result = self._get(
            module="account", action="txlist", address=address,
            startblock=0, endblock=99_999_999, page=1, offset=page_size, sort="desc",
        )
        if not isinstance(result, list):
            return [], False

        truncated = len(result) >= page_size
        out = []
        for tx in result:
            # A contract creation has an empty `to` and a populated contractAddress.
            if tx.get("to") in ("", None) and tx.get("contractAddress"):
                out.append(
                    {
                        "address": tx["contractAddress"],
                        "tx_hash": tx.get("hash", ""),
                        "timestamp": _ts(tx.get("timeStamp")),
                        "succeeded": tx.get("isError") in ("0", None, ""),
                    }
                )
                if len(out) >= limit:
                    truncated = truncated or True
                    break
        return out, truncated

    def first_activity(self, address: str) -> tuple[datetime | None, str | None]:
        """When this address first transacted, and who funded it."""
        result = self._get(
            module="account", action="txlist", address=address,
            startblock=0, endblock=99_999_999, page=1, offset=1, sort="asc",
        )
        if not isinstance(result, list) or not result:
            return None, None
        first = result[0]
        funder = first.get("from") if (first.get("to") or "").lower() == address.lower() else None
        return _ts(first.get("timeStamp")), funder

    def call(self, address: str, selector: str) -> str | None:
        """eth_call a zero-argument getter. Returns the raw hex result."""
        try:
            result = self._get(
                module="proxy", action="eth_call", to=address, data=selector, tag="latest"
            )
        except AuthError:
            raise
        except SourceError:
            # A contract without this getter is a normal answer, not a failure.
            return None
        if isinstance(result, str) and result.startswith("0x") and len(result) > 2:
            return result
        return None


def _ts(raw) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def decode_address(word: str | None) -> str | None:
    """Pull an address out of a 32-byte eth_call return value."""
    if not word or not word.startswith("0x") or len(word) < 42:
        return None
    return "0x" + word[-40:]


def decode_uint(word: str | None) -> int | None:
    if not word or not word.startswith("0x"):
        return None
    try:
        return int(word, 16)
    except ValueError:
        return None


def decode_string(word: str | None) -> str:
    """Decode an ABI-encoded string return value, tolerating bytes32 names."""
    if not word or not word.startswith("0x"):
        return ""
    raw = word[2:]
    try:
        data = bytes.fromhex(raw)
    except ValueError:
        return ""
    if len(data) >= 64:
        length = int.from_bytes(data[32:64], "big")
        if 0 < length <= len(data) - 64:
            return data[64 : 64 + length].decode("utf-8", errors="replace").strip()
    # bytes32-style: trailing nulls, decode what is there.
    return data.rstrip(b"\x00").decode("utf-8", errors="replace").strip()
