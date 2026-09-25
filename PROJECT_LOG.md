# SOC Home Lab — Project Log

A personal detection-and-response (Blue Team) lab built on Wazuh, Suricata,
a Cowrie honeypot, an AI-assisted alert triage pipeline, and
Greenbone/OpenVAS as a second vulnerability management source.

> This log documents the design, the real incidents hit while building it,
> and the troubleshooting decisions made along the way — not just the final
> result. The goal is to show process, not just output.

---

## 1. Architecture

Three nodes connected over Tailscale (private overlay network):

| Node | Role | Notes |
|---|---|---|
| Windows host | Monitored endpoint | Sysmon (SwiftOnSecurity config) + Wazuh agent |
| Ubuntu VM (VirtualBox) | SOC core | Wazuh Manager/Indexer/Dashboard, Suricata IDS, Grafana, Greenbone/OpenVAS |
| Cloud VPS | Honeypot | Cowrie (fake SSH, port 22), real access on an alternate port |

Private (RFC1918) networking between nodes via Tailscale; only the honeypot
exposes a real port to the Internet — by design, that's its job.

## 2. Wazuh — Detection

- Wazuh Manager + Indexer + Dashboard, single-node, on the Ubuntu VM.
- Suricata as network IDS, alerts ingested by Wazuh.
- ~62 custom rules in `local_rules.xml`, grouped into:
  - SSH/FTP brute force, crypto miner detection, hidden processes
  - Sysmon detection chain: obfuscated PowerShell, WMIC, CertUtil, RDP,
    credential dumping, persistence (using `frequency`/`timeframe` to cut
    down repetition noise)
  - Masquerading detection (T1036): system-named process running outside
    `System32`
  - Tuning rules for known false positives (see section 5)
- Alerts at level ≥10 trigger an AI-assisted analysis pipeline (section 4).

## 3. Honeypot (Cowrie)

- Cowrie running as a persistent systemd service on a low-cost cloud VPS,
  listening on the standard SSH port (22) to attract real automated scanning
  traffic from the Internet.
- Actual admin access to the VPS uses an alternate SSH port, with a
  passphrase-protected key.
- Custom rules (range 100200–100213) categorize honeypot events separately
  from the rest of the ruleset.
- Grafana dashboard ("Top IPs — Successful Honeypot Logins") showing: source
  IPs, critical alerts, attacker-executed commands, and a ranking of
  Suricata noise signatures for ongoing false-positive tuning.

## 4. AI Triage Pipeline (Wazuh → Gemini → Telegram)

A native Wazuh integration script (`custom-gemini.py`) that:

1. Triggers for alerts at level ≥10 with a rule ID starting with `100`.
2. Sends an immediate base message to Telegram (alert received).
3. Sends the full alert to the Gemini API with a structured Tier-2 SOC
   analyst prompt (severity, MITRE ATT&CK mapping, extracted IOCs,
   recommended hunting queries, false-positive assessment).
4. Sends the completed analysis back to Telegram.
5. Logs everything locally for audit purposes.

**Incident found and fixed (2026-07-31):** step 4 never actually ran — the
Gemini analysis was generated correctly but only written to the local log,
never re-sent to Telegram. Alerts stayed indefinitely in an "AI analysis in
progress" state with no visible resolution for the analyst. Root cause: the
final send-to-Telegram call was simply missing after the logging block.
Fixed by adding the missing call, with exception handling so a Telegram
failure doesn't break the logging step.

**Readability fix (2026-07-31):** messages were arriving as unformatted
plain text. Gemini outputs Markdown using `**bold**` (double asterisk,
standard CommonMark), but Telegram's classic `Markdown` parse mode expects a
single asterisk. Enabled `parse_mode=Markdown` on send and normalized the
analysis formatting before sending. The base message was also restructured
with visual separators and bolded fields.

All changes were made with a dated backup before each edit and a syntax
check (`py_compile`) before reloading the service.

## 5. False Positives Identified and Fixed (2026-07-31)

While investigating ~40 level-14 alerts (rule 100120, "Registry
Modification") received in a short window with no manual user activity:

- **Actual cause:** an AI app installed as a Windows Store package
  registering a file-explorer context-menu entry on auto-update. Parent
  process signed by Microsoft, `Medium` integrity, always the same 3-key
  registry pattern.
- **Related secondary false positive:** a base Sysmon rule (level 15,
  "Executable file dropped in malware-common folder") firing on
  `__PSScriptPolicyTest_*.ps1` files — PowerShell's own native execution
  policy check at startup, not malware.

**Fix:** rather than editing the base ruleset (overwritten on Wazuh
updates), two child rules were added to `local_rules.xml` that specifically
intercept those two exact patterns and lower their level to 3
(informational, doesn't trigger Telegram), leaving the original detection
behavior untouched for any other case.

Verified with `wazuh-analysisd -t` before restarting the service.

## 6. Greenbone / OpenVAS — Installation and Troubleshooting (2026-07-31)

### Context
A second vulnerability management source, complementing Wazuh, deployed via
the official Docker Compose stack (Community Edition), installed inside the
same SOC Ubuntu VM (resources verified sufficient before starting).

### Real Incidents During Installation

**1. Port 443 conflict.**
When bringing up the full stack, the Greenbone `nginx` container failed:
`address already in use` on `127.0.0.1:443`. Diagnosis: Wazuh Dashboard (a
Node.js process) was already listening on port 443 across all interfaces.
Fix (least invasive, without touching Wazuh in production): remap
Greenbone's nginx to `8443` in `compose.yaml`, with a backup taken first.

**2. `gvmd` crash loop during SCAP/CVE sync.**
`gvmd` kept aborting (`Aborted` signal, no OOM) always at the same point:
processing `nvd-cpe-matches.json.gz` (one of the heaviest files in the NVD
feed). Ruled out as causes: container memory (227 MiB actual usage, well
under the limit) and disk space (56% used, with headroom).

Actual root cause: the `scap-data` container (which extracts the feed into
a shared volume) had died (`ExitCode 255`) during a host laptop suspend
mid-way through a ~7 GB extraction, leaving the volume in a partial,
inconsistent state. `gvmd` was trying to read from that incomplete volume
and aborting.

Fix: restarted `scap-data` alone, waited for it to complete a full
extraction cycle (confirmed via `docker inspect` healthcheck), then
restarted `gvmd` — sync completed with no further aborts.

**3. 404 on `/login` after a healthy startup.**
With the whole stack healthy, the web UI returned `404 Not Found` on
`/login`. Ruled out: broken SSH tunnel, nginx down, misconfigured proxy
(`curl` straight to `gsad` from inside the `nginx` container returned the
same 404, isolating the issue to the application layer, not the network).
Actual cause: the `gsad` (v27) frontend is a SPA — `/login` routing is
handled client-side by JavaScript after the root `/` loads, not by a server
route. The correct URL for first access is the site root, not `/login`
directly.

**4. `admin` password reset.**
The auto-generated password from first startup was never captured (lost to
an SSH session drop). Manually reset via `gvmd --user=admin
--new-password=...`, run inside the container as the correct system user
(`gvmd`, not root — the initial attempt as root failed with `Permission
denied` on the database semaphore).

### Current Status
Full stack operational: web UI reachable via SSH tunnel at
`https://127.0.0.1:8443/`, login working, SCAP/CVE feed synced.

### Pending
- Configure a first test scan against a lab-owned target.
- Finalize repository naming convention before publishing (done: chose
  `openvas-homelab` for recognizability).

## 7. General Lab Backlog

- Confirm which port Wazuh Dashboard is actually listening on (official
  docs didn't match observed behavior — see incident 6.1).
- Pending `systemctl daemon-reload` after a unit file change for
  `wazuh-dashboard.service`.
- Investigate the trigger for rule 100188 (level 14, "File Deletion
  Activity") on the Windows endpoint — pending correlation with Sysmon
  Event ID 23.

---

## A Note on This Document

This log was written for public release. The following have been omitted
or redacted: credentials (bot tokens, API keys), personal device/network
names, and details that would identify the physical location of the
infrastructure. Private IP addresses shown (RFC1918 ranges) are standard
lab addressing and don't represent a risk on their own.

## 8. Known Upstream Bug — `gvmd:stable` Report Rendering (2026-08-01)

### Symptom
After a successful scan (`Scan-Workstation`, target `192.168.1.56`, completed
100% in ~12 minutes), attempting to view the report through any access path
— the web UI ("Reports" overview), the "Results" tab, and the GMP protocol
directly via `gvm-tools`/`gvm-cli` — consistently failed. The web UI showed
`GMP error during authentication` or `Failure to receive response from
manager daemon`; the CLI attempt got `Remote closed the connection`.

### Root Cause Analysis
`gvmd` logs showed a repeatable PostgreSQL error on every single attempt,
regardless of access method:
Tracing this to the `gvmd` source (`src/manage_pg.c`), the query is built
using a C preprocessor macro: `G_STRINGIFY(SEVERITY_ERROR)`. This macro is
meant to be expanded into a numeric literal (e.g. `-3.0`) at **compile
time**. The fact that the literal text `SEVERITY_ERROR` reached PostgreSQL
unexpanded means the macro was undefined when this specific `gvmd:stable`
image (pulled 2026-07-29) was built — a genuine compile-time defect baked
into that image, not a configuration issue on this deployment.

This was cross-referenced against a documented pattern in the same
codebase: GitHub issue greenbone/gvmd#2273 shows an earlier, structurally
identical class of bug — a broken materialized view definition
(`result_vt_epss`) causing the exact same failure mode ("fresh docker
deploy" + "reports completely inaccessible") in an earlier release. This
confirms report-breaking SQL/compile regressions are a recurring category
of issue in this project's Docker image releases, not a one-off.

### Ruled Out
- Container health/crash-looping: `gvmd` stayed `Up`/`healthy` at the
  Docker level throughout — only an internal worker process aborted per
  request, not the whole container.
- Memory: 2.4+ GiB free, 9+ GiB available, 0 swap in use at time of failure.
- The `pg-gvm` PostgreSQL extension (queried directly via
  `pg_available_extension_versions`): confirmed present, version 22.6, no
  newer version available in this image — a red herring initially
  suspected as the cause, ruled out once the bug was traced to a
  compile-time C macro rather than a runtime SQL extension function.

### Mitigation Attempted: Version Pinning (Failed — Documented for Completeness)
Attempted to pin `gvmd` to a release predating 2026-07-29 to sidestep the
regression. The official registry
(`registry.community.greenbone.net/community/gvmd`) was queried directly
for its full tag list:
No semantically versioned tags (e.g. `26.28.0`) or an `oldstable` tag are
published for `gvmd` in this registry, unlike some other Greenbone images.
Pinning to a known-good version is therefore not possible through this
distribution channel. This rules out the simplest remediation path.

### Status
**Open, unresolved, upstream defect.** The scanning engine itself
(`openvas-scanner`/`ospd-openvas`) completed the scan correctly — this
confirms the detection layer works. The defect is isolated entirely to
`gvmd`'s report-serving code path in this specific image build. No
user-side fix is available without recompiling `gvmd` from source with a
corrected macro definition, which is out of scope for this lab.

### Next Steps
- Re-test after the next `gvmd:stable` image publication, in case upstream
  ships a corrected build.
- Consider filing an issue against `greenbone/gvmd` referencing this
  reproduction, if not already reported.

### Reproducibility Confirmation (Second Scan, Same Day)
Ran a second, independent scan (`Scan-VM-SOC`, self-scan against the SOC VM
itself, `192.168.56.103`) to confirm the bug wasn't specific to the first
target. Task lifecycle (`New → Requested → Queued → Running → Done`)
completed cleanly with no errors — reconfirming the scanning engine itself
is fully functional.

Attempted three separate access paths to this second report:
1. Web UI report view — same `Failure to receive response from manager
   daemon` error.
2. GMP CLI export in XML format — same crash.
3. GMP CLI export in CSV format (`format_id` for "CSV Results") — same
   crash, identical backtrace (same memory offsets), confirming the defect
   is format-independent and lives entirely in the severity-counting logic
   shared by all report output paths, not in a specific export renderer.

This rules out any target-specific or report-specific data as the trigger:
the bug fires unconditionally whenever `gvmd` attempts to build the results
severity summary for **any** report, regardless of scan target or export
format requested.

### Resolution (Same Day, Later)
Found a viable workaround by tracing the failure to its exact mechanism:
PostgreSQL was interpreting the unexpanded `SEVERITY_ERROR` macro as an
unquoted reference to a column named `severity_error` on the `results`
table. Rather than reproducing the intended numeric constant (`-3.0`, the
project's documented "Error" severity value) as a real column would let
PostgreSQL resolve the query as originally intended by the (correctly
compiled) SQL logic — without needing to patch or recompile the `gvmd`
binary itself.

**Fix applied** (additive, non-destructive, reversible):
```sql
ALTER TABLE results ADD COLUMN severity_error real DEFAULT -3.0 NOT NULL;
```

A full `pg_dump` backup (1.79 GB) was taken before this change.

**Verified working** via GMP CLI (`get_reports` returned `status="200"`)
and confirmed visually in the web UI: Dashboards, the Reports list, and
individual report details (results, host, EPSS score) all render
correctly for both scans performed today.

### Lessons Learned
- A compile-time defect in vendor-shipped software can sometimes be
  worked around at the data layer, without needing source access or a
  rebuild — by understanding precisely how the broken query is
  misinterpreting the schema.
- Always validate a hypothesis about a database-level workaround with a
  full backup and a narrowly-scoped, additive schema change (`ADD COLUMN`
  with a default, not modifying or dropping anything existing).
- This workaround is scoped to this specific `gvmd` image build. It
  should be re-evaluated (and likely removed) if the image is upgraded,
  in case a future release fixes the root cause differently.

## 9. Operational Finding: VM Restarts Reset the VT Cache (2026-08-01)

### Symptom
A third target/task setup (`Scan-Workstation`) repeatedly returned zero
results (`hosts: 0`, `result_count: 0`) across multiple attempts, despite
the target host being reachable (`ping` succeeded consistently).

### Root Cause #1 (unrelated, found along the way): Target IP typo
Direct inspection of the `targets` table in PostgreSQL revealed the actual
configured host was `196.168.1.56`, not `192.168.1.56` — a single-digit
transcription error made when the target was first created. The web UI's
"Edit Target" host field was greyed out and non-editable in this Greenbone
version, so the fix was to delete the misconfigured target and recreate it
cleanly rather than edit in place. Confirmed via `openvas` scan engine logs
(`libgvm boreas`) explicitly reporting `Target has 1 hosts: 196.168.1.56`
and `0 alive hosts of 1` — the engine was behaving completely correctly;
it was simply given the wrong IP.

### Root Cause #2: VT cache reset after VM reboot
While correcting the target, the underlying Ubuntu VM was found to have
rebooted (`last -x` showed a `reboot system boot` entry, with a ~6 hour
gap in session activity beforehand — likely the host laptop sleeping
unattended). Every VM reboot forces `ospd-openvas` to reload its full
Vulnerability Test (VT) plugin cache from scratch, which — as already
observed twice this week — takes approximately **45–50 minutes**. Any
scan task started before this completes queues silently with no error
shown to the user; from the UI it is indistinguishable from a task that
is legitimately just slow.

### Operational Takeaway
In a production setting with fixed daily scanning windows, the VT reload
time must be budgeted at the start of each session if the scanning host
was powered off or suspended since the last one.

## 10. Session Timeout Configuration (2026-08-01)

### Problem
The web UI logged out automatically after ~15 minutes of inactivity,
interrupting work sessions.

### Investigation
`gsad` supports a `--timeout` CLI flag (minutes of idle time before
session expiry, default 15). The container's environment variables follow
a `GSAD_*` naming convention (`GSAD_HTTP_ONLY`, `GSAD_API_ONLY`,
`GSAD_FOREGROUND`), which initially suggested a `GSAD_TIMEOUT` variable
would work directly.

**First attempt (failed):** Set `GSAD_TIMEOUT: "120"` as an environment
variable. Confirmed via `docker exec ... env` that the variable was
present inside the container, but the startup log still showed
`starting gsad with args -f --http-only` — the value was never picked up.

**Second attempt (failed, more invasive):** Overrode the Compose
`command:` directly with `["-f", "--http-only", "--timeout=120"]`. This
broke the container entirely (`exec: "-f": executable file not found in
$PATH`) — inspecting the image's actual entrypoint
(`docker inspect ... --format='{{.Config.Entrypoint}} {{.Config.Cmd}}'`)
showed the real command is a wrapper script
(`/usr/local/bin/start-gsad`), not `gsad` directly. Overriding `command:`
replaced that wrapper script entirely instead of passing arguments to it.

### Root Cause
Read the wrapper script directly from the image
(`docker run --rm --entrypoint cat <image> /usr/local/bin/start-gsad`):
it reads a variable named **`GSAD_ARGS`** (not `GSAD_TIMEOUT`) and, if
unset, defaults to `-f --http-only`. No individual `GSAD_TIMEOUT`
variable exists — the image only exposes a single combined args string.

### Fix
Reverted the broken `command:` override. Set the correct variable:
```yaml
environment:
  GSAD_ARGS: "-f --http-only --timeout=120"
```
Recreated with `docker compose up -d --no-deps gsad` (the `--no-deps`
flag avoids re-triggering unrelated data-feed containers mid-cycle, which
had caused a separate `unhealthy` dependency failure on an earlier
attempt).

Verified in the startup log: `starting gsad with args -f --http-only
--timeout=120`.

### Lesson
When an image's env-var naming convention suggests a mapping
(`GSAD_HTTP_ONLY` → `--http-only`) but no documentation confirms it for
every flag, read the actual entrypoint/wrapper script from the image
before assuming a variable name — guessing cost two failed iterations
here before finding `GSAD_ARGS`.

## 11. Remote Access Setup and First Remediation Cycle (2026-08-02)

### Goal
Establish repeatable remote access to the scanned Windows workstation
(`192.168.1.56`) to apply the Medium-severity finding fix (open RPC/DCOM
port 135/tcp) identified in the first scan, without requiring physical
access to the machine for future work.

### Attempt 1: PowerShell Remoting (WinRM) — Abandoned
Enabled `Enable-PSRemoting -Force` on the target; confirmed WinRM service
running and listener active on port 5985. Configured `TrustedHosts` on
the connecting laptop (required for workgroup, non-domain environments).

Connection consistently failed with "Access Denied", despite the
connecting account being a confirmed local administrator
(`net localgroup administradores` showed the account listed). Root cause
was not fully isolated (likely Windows Hello / online-account credential
mismatch — see below), but troubleshooting was stopped in favor of a
more broadly useful method: SSH is already the standard access method
used across the rest of this lab (Linux VM, honeypot), so standardizing
on it for Windows as well reduces tooling fragmentation — directly
relevant when applying the same skillset in a production environment.

### Attempt 2: OpenSSH Server — Successful
Installed the native Windows OpenSSH Server capability:
Confirmed firewall rule "OpenSSH SSH Server (sshd)" enabled automatically
by the installer.

**Credential issue found:** the primary account (`personal-account`) is a Microsoft
(online) account, not a true local Windows account. Attempting to reset
its password via `net user personal-account *` failed with "the system is not
authoritative for this account" — a well-known Windows behavior:
online-account passwords cannot be reset locally.

**Resolution:** created a dedicated local administrator account solely
for lab/SSH access, decoupled from the personal Microsoft account:
SSH connection from the laptop confirmed successful (`ssh soclab@192.168.1.56`),
with full administrative privileges verified via `whoami /priv`.

### Note: SSH Session Shell
By default, the SSH session lands in `cmd.exe`, not PowerShell — commands
must be prefixed with `powershell -Command "..."` or the default shell
reconfigured. (Follow-up planned to set PowerShell as the default SSH
shell for convenience.)

### Remediation Applied: Medium Finding (RPC/DCOM Port 135)
Diagnosed which firewall rule was actually permitting inbound traffic on
port 135 (multiple RPC/DCOM-related rules exist on Windows by default,
most disabled). Isolated the single active, permissive rule:

- **Rule:** "Asistencia remota (DCOM de entrada)"
- **Before:** `Enabled: True`, `RemoteAddress: Any`
- **Fix applied:**
- **Verified after:** `RemoteAddress: 192.168.1.0/255.255.255.0` (equivalent
  to /24) — confirmed via `Get-NetFirewallAddressFilter`.

This restricts Remote Assistance/DCOM traffic to the local trusted subnet
instead of accepting connections from any source.

### Note: Agentless Remediation at Scale

Scanning and remediation have different requirements on the target: an
agentless scan never touches the system, but remediation always needs
some execution mechanism on it. For a domain-joined fleet, the
no-additional-install approach is:

- **Windows:** Group Policy (GPO), using the existing Active
  Directory infrastructure — no per-host software install.
- **Linux:** Ansible — agentless, relying only on SSH + Python; a
  control node applies changes in parallel across hosts.

### Pending Verification
A follow-up scan against `192.168.1.56` is queued to confirm the finding
is resolved, pending the OpenVAS engine completing its VT cache reload
after another VM restart (see section 9 — this is now a well-understood,
recurring operational constraint of this lab).

### PowerShell as Default SSH Shell
Set PowerShell as the default shell for new SSH sessions (instead of the
default `cmd.exe`), via registry:
Verified by reconnecting: new sessions now land directly in a `PS>`
prompt, removing the need to prefix every command with
`powershell -Command "..."`.

**Remote access setup for `192.168.1.56` is now complete and reusable**
for future work sessions: SSH auto-starts on boot, dedicated local admin
account (`soclab`) is decoupled from the personal Microsoft account, and
PowerShell is the default interactive shell.

### Verification Scan Result (2026-08-02)
Re-scanned `192.168.1.56` after applying the firewall fix. Result: **2
findings**, down from the original scope of informational-only results
plus the Medium finding — the Medium finding (port 135/tcp) still
appears at the same severity (5.0 Medium).

**This is expected, not a failed fix.** The OpenVAS scanner itself runs
from the lab VM, which reaches the target via the same
`192.168.1.0/24` subnet that the firewall rule was configured to allow
(`Set-NetFirewallRule ... -RemoteAddress 192.168.1.0/24`). The fix
correctly restricts access to *outside* that trusted subnet — it was
never meant to block the scanner itself, which sits inside it. The fix
was already independently confirmed applied via
`Get-NetFirewallAddressFilter` (showed `192.168.1.0/255.255.255.0`
instead of `Any`) in section 11. A true external-network verification
would require scanning from outside `192.168.1.0/24`, which is out of
scope for this lab session.

**New finding surfaced:** *Weak MAC Algorithm(s) Supported (SSH)*,
Low severity, port 22/tcp — a direct consequence of today's OpenSSH
Server installation (default `sshd_config` enables some legacy MAC
algorithms). Real and valid finding; not yet remediated.

### Pending for Next Session
- Harden `sshd_config` on `192.168.1.56` to disable weak MAC algorithms
  (Low severity finding from today's verification scan).

## 12. SSH Hardening: Weak MAC Algorithms Fix (2026-08-02/03)

### Problem
Verification scan flagged "Weak MAC Algorithm(s) Supported (SSH)" (Low
severity, port 22/tcp) on `192.168.1.56` — a direct result of installing
OpenSSH Server earlier in the day with its default configuration, which
enables some legacy MAC algorithms for backward compatibility.

### Fix Attempt 1 (failed, caught before service restart)
Backed up `sshd_config`, then appended `MACs`, `Ciphers`, and
`KexAlgorithms` directives to the end of the file using `Add-Content`.

Syntax check (`sshd.exe -t`) caught the error before any service
disruption:
Root cause: the file ends with a `Match Group administrators` block
(scoping `AuthorizedKeysFile` for that group). Appending new global
directives after a `Match` block places them *inside* its scope, where
connection-level directives like `MACs`/`Ciphers`/`KexAlgorithms` are not
permitted.

### Fix Attempt 2 (successful)
Rebuilt the file, inserting the three directives *before* the `Match`
block (after line 79, the `Subsystem sftp` line, and before line 87,
`Match Group administrators`) using PowerShell array slicing:
```powershell
$content = Get-Content "$env:ProgramData\ssh\sshd_config"
$newLines = @(
    "MACs hmac-sha2-256-etm@openssh.com,hmac-sha2-512-etm@openssh.com,hmac-sha2-256,hmac-sha2-512",
    "Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr",
    "KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group16-sha512"
)
$beforeMatch = $content[0..78]
$matchBlockOnward = $content[79..86]
($beforeMatch + $newLines + $matchBlockOnward) | Set-Content "$env:ProgramData\ssh\sshd_config"
```
Verified with `sshd.exe -t` (no output = valid syntax) before restarting
the service. `Restart-Service sshd` succeeded; reconnecting via
`ssh soclab@192.168.1.56` from the laptop confirmed the connection still
negotiates successfully with the restricted, modern algorithm set.

### Lesson
When appending directives to an OpenSSH config file that ends in a
`Match` block, new global directives must be inserted *before* that
block, not appended to the end of the file. Always validate with
`sshd -t` before restarting the service in an active remote session —
this caught the error with zero downtime.

### Pending Verification
Re-scan of `192.168.1.56` to confirm the "Weak MAC Algorithm(s)" finding
is resolved is queued, pending the OpenVAS engine's VT reload after
another VM restart (recurring constraint, see section 9).
