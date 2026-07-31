#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path

from scripts.infra.common import docker_is_supported_rootful, validate_deployment_id, volume_names


REQUIRED_SECRETS = ("db_admin_password", "db_password", "redis_password", "jwt_secret", "ai_internal_token")
OPTIONAL_FILE_SECRETS = ("deepseek_api_key", "dashscope_api_key", "tavily_api_key")


def validate_secret_files(secret_root: Path) -> dict[str, str]:
    all_secrets = (*REQUIRED_SECRETS, *OPTIONAL_FILE_SECRETS)
    missing = [name for name in all_secrets if not (secret_root / name).is_file()]
    if missing:
        raise ValueError(f"missing secrets: {missing}")

    values = {
        name: (secret_root / name).read_text(encoding="utf-8").strip()
        for name in all_secrets
    }
    weak = [
        name
        for name in REQUIRED_SECRETS
        if len(values[name]) < (64 if name in {"jwt_secret", "ai_internal_token"} else 16)
    ]
    if weak:
        raise ValueError(f"weak secrets: {weak}")

    noncanonical = []
    for name in all_secrets:
        raw = (secret_root / name).read_bytes()
        expected = ((values[name] + "\n") if values[name] else "").encode("utf-8")
        if raw != expected:
            noncanonical.append(name)
    if noncanonical:
        raise ValueError(f"secret files must use UTF-8 with one LF terminator: {noncanonical}")

    states = {name: "present" for name in REQUIRED_SECRETS}
    states.update({name: "configured" if values[name] else "empty" for name in OPTIONAL_FILE_SECRETS})
    return states


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment-id", default=os.getenv("KINLIN_DEPLOYMENT_ID", ""))
    parser.add_argument("--secrets-dir", default=os.getenv("KINLIN_SECRETS_DIR", ""))
    parser.add_argument("--bind-address", default=os.getenv("KINLIN_BIND_ADDRESS", "127.0.0.1"))
    parser.add_argument("--gateway-source-cidr", default=os.getenv("KINLIN_GATEWAY_SOURCE_CIDR", ""))
    parser.add_argument("--output")
    args = parser.parse_args()

    deployment_id = validate_deployment_id(args.deployment_id)
    supported, docker_detail = docker_is_supported_rootful()
    if not supported:
        raise SystemExit(docker_detail)
    address = ipaddress.ip_address(args.bind_address)
    if address.is_unspecified:
        raise SystemExit("binding Frontend to 0.0.0.0/:: is forbidden")
    firewall_required = not address.is_loopback
    if firewall_required:
        if not address.is_private:
            raise SystemExit("remote gateway mode requires a private management address")
        if not args.gateway_source_cidr:
            raise SystemExit("remote gateway mode requires KINLIN_GATEWAY_SOURCE_CIDR")
        ipaddress.ip_network(args.gateway_source_cidr, strict=False)

    secret_root = Path(args.secrets_dir)
    try:
        secret_states = validate_secret_files(secret_root)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    report = {
        "deploymentId": deployment_id,
        "docker": docker_detail,
        "bindAddress": str(address),
        "firewallRequired": firewall_required,
        "gatewaySourceCidr": args.gateway_source_cidr or None,
        "volumes": volume_names(deployment_id),
        "secrets": secret_states,
        "modelProviderConfigured": any(secret_states[name] == "configured" for name in OPTIONAL_FILE_SECRETS),
        "egressNotice": "agent-network permits outbound access; Backend and FastAPI may both have egress. Domain-level egress control is out of P0/P1 scope.",
    }
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
