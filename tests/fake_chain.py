"""A fake ChainSource, so contract research can be tested without an API key."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tradingbot.research.sources import SELECTORS, ZERO_ADDRESS, ChainSource, SourceError

NOW = datetime.now(timezone.utc)

# A contract with every dangerous power switched on.
RUGGY_SOURCE = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract MoonInu is Ownable {
    mapping(address => uint256) private _balances;
    mapping(address => bool) public blacklist;
    uint256 public buyTax = 5;

    function mint(address to, uint256 amount) external onlyOwner {
        _balances[to] = _balances[to] + amount;
        _totalSupply += amount;
    }

    function setFee(uint256 newFee) external onlyOwner {
        buyTax = newFee;
    }

    function setBlacklist(address a, bool v) external onlyOwner {
        blacklist[a] = v;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(!blacklist[from], "blocked");
    }
}
"""

# A plain, ownership-renounced token with nothing alarming in it.
CLEAN_SOURCE = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract PlainToken is ERC20 {
    constructor() ERC20("Plain", "PLN") {
        _mint(msg.sender, 1000000 ether);
    }

    function renounceOwnership() public onlyOwner {
        _transferOwnership(address(0));
    }
}
"""


class FakeChainSource(ChainSource):
    """Returns canned answers; every method can be made to fail."""

    def __init__(
        self,
        *,
        verified=True,
        source=RUGGY_SOURCE,
        name="MoonInu",
        proxy=False,
        implementation="",
        creator="0x" + "11" * 20,
        created_days_ago=2.0,
        owner="0x" + "22" * 20,
        deployments=None,
        deployer_first_seen_days=5.0,
        truncated=False,
        fail: set | None = None,
        token=("Moon Inu", "MOON", 18, 10**27),
    ):
        self.verified = verified
        self.source = source
        self.name = name
        self.proxy = proxy
        self.implementation = implementation
        self.creator = creator
        self.created_days_ago = created_days_ago
        self.owner = owner
        self.deployments = deployments if deployments is not None else []
        self.deployer_first_seen_days = deployer_first_seen_days
        self.truncated = truncated
        self.fail = fail or set()
        self.token = token
        self.calls = []

    def _guard(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise SourceError(f"{name} is unavailable")

    def source_code(self, address):
        self._guard("source_code")
        return {
            "SourceCode": self.source if self.verified else "",
            "ContractName": self.name if self.verified else "",
            "CompilerVersion": "v0.8.20+commit.a1b79de6" if self.verified else "",
            "LicenseType": "MIT" if self.verified else "",
            "ABI": "[]" if self.verified else "Contract source code not verified",
            "Proxy": "1" if self.proxy else "0",
            "Implementation": self.implementation,
        }

    def creation(self, address):
        self._guard("creation")
        created = NOW - timedelta(days=self.created_days_ago)
        return {
            "contractCreator": self.creator,
            "txHash": "0x" + "ab" * 32,
            "timestamp": str(int(created.timestamp())),
        }

    def deployments_by(self, address, limit=25):
        self._guard("deployments_by")
        return list(self.deployments)[:limit], self.truncated

    def first_activity(self, address):
        self._guard("first_activity")
        if self.deployer_first_seen_days is None:
            return None, None
        return NOW - timedelta(days=self.deployer_first_seen_days), "0x" + "ff" * 20

    def call(self, address, selector):
        self._guard("call")
        name, symbol, decimals, supply = self.token
        if selector == SELECTORS["owner"]:
            return None if self.owner is None else "0x" + self.owner[2:].rjust(64, "0")
        if selector == SELECTORS["getOwner"]:
            return None
        if selector == SELECTORS["decimals"]:
            return "0x" + format(decimals, "064x")
        if selector == SELECTORS["totalSupply"]:
            return "0x" + format(supply, "064x")
        if selector in (SELECTORS["name"], SELECTORS["symbol"]):
            text = (name if selector == SELECTORS["name"] else symbol).encode()
            body = text.hex().ljust(64, "0")
            return "0x" + format(32, "064x") + format(len(text), "064x") + body
        return None


def renounced_source(**kwargs):
    """A clean contract whose ownership has actually been renounced."""
    defaults = dict(
        source=CLEAN_SOURCE, name="PlainToken", owner=ZERO_ADDRESS,
        created_days_ago=400.0, deployer_first_seen_days=900.0,
    )
    return FakeChainSource(**{**defaults, **kwargs})
