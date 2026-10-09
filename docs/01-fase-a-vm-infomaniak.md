# Fase A — VM en Infomaniak, acceso solo por Tailscale

Fecha: 2026-10-08 · Estado: **completada** (pendiente snapshot `base-limpia`)

## Objetivo

Una VM dedicada (`soc-openvas-01`) para Greenbone, separada del Wazuh y del Grafana ya
en producción, accesible únicamente por Tailscale.

## Especificaciones

| Recurso | Valor | Mínimo oficial | Recomendado oficial |
|---|---|---|---|
| vCPU | 4 | 2 | 4 |
| RAM | 8 GB | 4 GB | 8 GB |
| Disco | 80 GB | 20 GB | 60 GB |
| SO | Ubuntu 24.04.5 LTS | | |

Flavor usado: `a4-ram8-disk80-perf1` (Infomaniak Public Cloud, OpenStack).

## Pasos

### A1 · Clave SSH dedicada `[Laptop · PowerShell]`

Se usó una clave exclusiva para esta VM; no se reutilizaron las de otras máquinas
(si una clave se compromete, solo afecta a un servidor).

```powershell
ssh-keygen -t rsa -b 4096 -f "$HOME\.ssh\infomaniak_openvas_rsa" -C "soc-openvas-01"
Get-Content "$HOME\.ssh\infomaniak_openvas_rsa.pub" | Set-Clipboard
```

> **Lo que falló:** primero se generó una clave `ed25519`; el panel de Infomaniak rechazó
> el import con "Impossible d'importer la paire de clés" aunque `ssh-keygen -l` la daba por
> válida. Con una clave RSA 4096 el import funcionó. Solo se sube la parte pública.

### A2 · Grupo de seguridad propio `[Panel Infomaniak]`

Se creó `sg-openvas` en lugar de reutilizar los grupos de otros servicios.

- Salida: IPv4 e IPv6 abiertas (necesaria para descargar los feeds de Greenbone).
- Entrada: solo SSH (TCP 22) desde la IP del administrador (`/32`), **temporal**.

> **Lo que falló:** la primera conexión dio `Connection timed out`. La regla del grupo tenía
> otra IP distinta a la IP pública real del administrador (el navegador usaba un VPN).
> Se comprobó con `(Invoke-WebRequest https://ifconfig.me/ip).Content` y se añadió la regla.

### A3 · Lanzar la instancia `[Panel Infomaniak]`

Instancia `soc-openvas-01`, clave importada, grupo `sg-openvas`.

### A4 · Primer acceso y verificación de recursos `[Laptop → VM]`

```powershell
ssh -i "$HOME\.ssh\infomaniak_openvas_rsa" ubuntu@<IP_PUBLICA>
```

```bash
nproc; free -h; df -h /; lsb_release -d
```

Resultado: 7,8 GiB de RAM, 75 GB libres, Ubuntu 24.04.5 LTS.

### A5 · Actualizar el sistema `[VM]`

```bash
sudo apt update && sudo apt upgrade -y
```

### A6 · Tailscale `[VM]`

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=soc-openvas-01
tailscale ip -4
```

Se aprobó el dispositivo desde el enlace de login. Se verificó el acceso SSH **por la IP de
Tailscale desde una segunda sesión**, dejando la primera abierta como respaldo.

### A7 · Firewall del sistema `[VM]`

Solo tras confirmar el SSH por Tailscale:

```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing && sudo ufw allow in on tailscale0
sudo ufw enable
sudo ufw status verbose
```

Resultado: política `deny (incoming)`, único permiso de entrada en la interfaz `tailscale0`.

**Cómo revertir:** `sudo ufw disable` (desde la sesión de respaldo).

### A8 · Cerrar el SSH público `[Panel Infomaniak]`

Se eliminaron las reglas de entrada SSH de `sg-openvas`. Desde ese momento la VM no acepta
conexiones entrantes desde internet. Se verificó con:

```powershell
ssh -i "$HOME\.ssh\infomaniak_openvas_rsa" ubuntu@<IP_TAILSCALE> "whoami"
```

### A9 · Snapshot `base-limpia` `[Panel Infomaniak]`

Punto de restauración antes de instalar nada más.

## Verificación de la fase

- [x] Acceso SSH solo por Tailscale
- [x] UFW activo, deny por defecto
- [x] Grupo de seguridad sin reglas de entrada
- [ ] Snapshot `base-limpia` (confirmar)
