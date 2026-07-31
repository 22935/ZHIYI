from scripts.infra.firewall import commands


def test_every_firewall_plan_has_backup_apply_and_rollback():
    for backend in ("firewalld", "nftables", "ufw"):
        plan = commands(backend, "10.20.0.0/24", "10.30.0.8", 8080)
        assert plan["backup"]
        assert plan["apply"]
        assert plan["rollback"]


def test_allow_rule_is_applied_before_deny_rule():
    for backend in ("firewalld", "nftables", "ufw"):
        apply_text = [" ".join(item) for item in commands(backend, "10.20.0.0/24", "10.30.0.8", 8080)["apply"]]
        allow_index = next(index for index, value in enumerate(apply_text) if "allow" in value or "accept" in value)
        deny_index = next(index for index, value in enumerate(apply_text) if "deny" in value or "drop" in value)
        assert allow_index < deny_index
