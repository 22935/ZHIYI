#!/usr/bin/env python3
"""Preview/apply/rollback a reversible remote-gateway firewall restriction."""

from __future__ import annotations

import argparse
import ipaddress
import json
import shutil
import shlex
import subprocess
from pathlib import Path


def backend() -> str:
    for name, command in (("firewalld", "firewall-cmd"), ("nftables", "nft"), ("ufw", "ufw")):
        if shutil.which(command):
            return name
    raise SystemExit("no supported firewall backend found")


def commands(kind: str, source: str, address: str, port: int):
    if kind == "firewalld":
        allow = f'rule family="ipv4" priority="-10" source address="{source}" destination address="{address}" port port="{port}" protocol="tcp" accept'
        deny = f'rule family="ipv4" priority="10" destination address="{address}" port port="{port}" protocol="tcp" drop'
        return {
            "backup": [["firewall-cmd", "--list-all", "--permanent"]],
            "apply": [["firewall-cmd", "--permanent", "--add-rich-rule", allow], ["firewall-cmd", "--permanent", "--add-rich-rule", deny], ["firewall-cmd", "--reload"]],
            "rollback": [["firewall-cmd", "--permanent", "--remove-rich-rule", deny], ["firewall-cmd", "--permanent", "--remove-rich-rule", allow], ["firewall-cmd", "--reload"]],
        }
    if kind == "ufw":
        return {
            "backup": [["ufw", "status", "numbered"]],
            "apply": [["ufw", "insert", "1", "allow", "from", source, "to", address, "port", str(port), "proto", "tcp"], ["ufw", "insert", "2", "deny", "to", address, "port", str(port), "proto", "tcp"]],
            "rollback": [["ufw", "--force", "delete", "deny", "to", address, "port", str(port), "proto", "tcp"], ["ufw", "--force", "delete", "allow", "from", source, "to", address, "port", str(port), "proto", "tcp"]],
        }
    table = "kinlin_gateway_v11"
    return {
        "backup": [["nft", "list", "ruleset"]],
        "apply": [["nft", "add", "table", "inet", table], ["nft", "add", "chain", "inet", table, "input", "{ type filter hook input priority -5; policy accept; }"] , ["nft", "add", "rule", "inet", table, "input", "ip", "daddr", address, "tcp", "dport", str(port), "ip", "saddr", source, "accept"], ["nft", "add", "rule", "inet", table, "input", "ip", "daddr", address, "tcp", "dport", str(port), "drop"]],
        "rollback": [["nft", "delete", "table", "inet", table]],
    }


def execute(items: list[list[str]], *, output=None, check: bool = True) -> None:
    for command in items:
        completed = subprocess.run(command, check=check, text=True, capture_output=True)
        if output is not None:
            output.write("$ " + " ".join(command) + "\n" + completed.stdout + completed.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "apply", "rollback"))
    parser.add_argument("--source")
    parser.add_argument("--address")
    parser.add_argument("--port", type=int)
    parser.add_argument("--state", required=True)
    parser.add_argument("--validation-command", help="non-shell command that must succeed after applying rules")
    parser.add_argument("--firewall-backend", choices=("firewalld", "nftables", "ufw"), help="plan against a named backend even when it is not installed locally")
    args = parser.parse_args()
    state_path = Path(args.state)
    if args.action == "rollback":
        saved = json.loads(state_path.read_text(encoding="utf-8").splitlines()[0])
        plan = commands(saved["backend"], saved["source"], saved["address"], saved["port"])
        execute(plan["rollback"], check=False)
        print(json.dumps({"status": "rolled-back", "state": str(state_path), "originalRulesBackup": "preserved-in-state"}))
        return 0
    if not args.source or not args.address or not args.port:
        parser.error("plan/apply require --source, --address and --port")
    ipaddress.ip_network(args.source, strict=False)
    ipaddress.ip_address(args.address)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    kind = args.firewall_backend or backend()
    plan = commands(kind, args.source, args.address, args.port)
    if args.action == "plan":
        print(json.dumps({"backend": kind, **plan, "validationCommand": args.validation_command}, ensure_ascii=False, indent=2))
        return 0
    if not args.validation_command:
        raise SystemExit("apply requires --validation-command; rules are never changed without post-apply validation")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as state:
        state.write(json.dumps({"backend": kind, "source": args.source, "address": args.address, "port": args.port, "manualRecovery": "run this script with rollback --state <file>"}) + "\n")
        execute(plan["backup"], output=state)
    try:
        execute(plan["apply"])
        # Capture the installed rule set, then require a caller-supplied reachability check.
        execute(plan["backup"])
        subprocess.run(shlex.split(args.validation_command), check=True)
    except Exception:
        execute(plan["rollback"], check=False)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
