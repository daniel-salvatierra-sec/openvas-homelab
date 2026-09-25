# SOC Home Lab — Wazuh · Suricata · Cowrie · OpenVAS

Personal Blue Team lab built from scratch to practice detection,
alert triage and vulnerability management.

## Architecture

| Node | Role | Stack |
|---|---|---|
| Windows 11 host | Monitored endpoint | Sysmon (SwiftOnSecurity) + Wazuh agent |
| Cloud VM (Switzerland) | SOC core | Wazuh Manager/Indexer/Dashboard, Suricata, Grafana, Greenbone/OpenVAS |
| Cloud VPS | Honeypot | Cowrie SSH honeypot exposed to the Internet |

Nodes connected over Tailscale.

## Highlights

- ~62 custom Wazuh detection rules (Sysmon chain: PowerShell, WMIC,
  CertUtil, RDP, credential dumping, persistence), mapped to MITRE ATT&CK
- AI-assisted triage pipeline: Wazuh → Gemini API → Telegram for
  critical alerts
- False-positive tuning with child rules, without editing the base ruleset
- Greenbone/OpenVAS on Docker, including a data-layer workaround for an
  upstream `gvmd` compile-time defect
- Full scan → remediate → verify cycle (firewall scoping, SSH
  cipher/MAC hardening)

## Documentation

Full engineering log (incidents, root causes, fixes, lessons learned):
[PROJECT_LOG.md](PROJECT_LOG.md)

> Credentials, personal device names and location details are redacted.
