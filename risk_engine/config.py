from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .rules import AccountVolumeLimitRule, BaseRule, OrderRateLimitRule


@dataclass(slots=True)
class RiskConfig:
    contract_to_product: Dict[str, str]
    rules: List[BaseRule]


def build_config(config_dict: dict) -> RiskConfig:
    contract_to_product = config_dict.get("contract_to_product", {})

    rules: List[BaseRule] = []
    for r in config_dict.get("rules", []):
        rtype = r.get("type")
        if rtype == "OrderRateLimitRule":
            rules.append(
                OrderRateLimitRule(
                    threshold_per_account=int(r.get("threshold", 50)),
                    window_ns=int(r.get("window_ns", 1_000_000_000)),
                    bucket_ns=int(r.get("bucket_ns", 1_000_000)),
                )
            )
        elif rtype == "AccountVolumeLimitRule":
            rules.append(
                AccountVolumeLimitRule(
                    daily_cap=int(r.get("daily_cap", 1000)),
                    dimensions=tuple(r.get("dimensions", ["account"])),
                )
            )
        else:
            raise ValueError(f"unknown rule type: {rtype}")

    return RiskConfig(contract_to_product=contract_to_product, rules=rules)