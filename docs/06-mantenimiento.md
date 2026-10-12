# Mantenimiento

Registro de las tareas de mantenimiento del escáner, con la fecha, el motivo y cómo revertir.

## 2026-10-12 · Kernel nuevo y reinicio de la VM del escáner

**Motivo:** el agente Wazuh de la VM reportaba CVE del kernel instalado (`6.8.0-124`). El kernel
`6.8.0-146` ya estaba instalado por un `apt upgrade` anterior; faltaba reiniciar para usarlo
(`/var/run/reboot-required`, que también listaba `libc6`).

**Antes de tocar nada:**

1. Snapshot de la VM (`openvas-prekernel-AAAAMMDD`) con la columna *Task* de la instancia en `Aucun`.
2. Comprobación de solo lectura: kernel actual, reinicio pendiente, paquetes actualizables,
   disco libre y **política de reinicio de los contenedores**.

```bash
uname -r; ls /var/run/reboot-required*; cat /var/run/reboot-required.pkgs
dpkg -l 'linux-image-[0-9]*' | awk '/^ii/{print $2, $3}'
docker inspect -f '{{.Name}} {{.HostConfig.RestartPolicy.Name}}' $(docker ps -q)
```

**Hallazgo importante:** en el compose oficial de Greenbone, los 7 servicios (`gvmd`, `gsad`,
`nginx`, `pg-gvm`, `ospd-openvas`, `openvasd`, `redis-server`) tienen política `always`, pero los
7 contenedores de datos de feeds (`vulnerability-tests`, `scap-data`, `notus-data`,
`cert-bund-data`, `dfn-cert-data`, `data-objects`, `report-formats`) tienen `no`. Tras un
reinicio los servicios arrancan solos con los datos ya guardados en los volúmenes, pero los
contenedores de feeds no.

**Reinicio:**

```bash
sudo reboot
# esperar ~2 min; tailscale ping <IP_TAILSCALE>; ssh
uname -r                                  # 6.8.0-146-generic
systemctl is-active tailscaled wazuh-agent docker
sudo ufw status | head -1
docker compose -f ~/greenbone-community-edition/compose.yaml up -d   # levanta los contenedores de datos
```

**Resultado:** kernel `6.8.0-146`, sin reinicio pendiente, Tailscale, Wazuh y Docker `active`,
UFW activo, los 16 servicios `Up` y los de datos `healthy` tras unos 12 minutos. El agente
Wazuh se reconectó solo al manager de demo (ID 003, `Active`).

**Tras un reinicio, Greenbone tarda 45-50 minutos en recargar la caché de VTs.** No se lanzan
escaneos hasta que *Administration → Feed Status* muestre NVT, SCAP, CERT y GVMD_DATA en
*Current*.

**Cómo revertir:** restaurar el snapshot previo desde el panel. El kernel antiguo (`-124`) sigue
instalado y se puede elegir en el menú de arranque.

**Después:** cuando el kernel nuevo lleve unos días estable, borrar el snapshot previo (80 GB
cuentan contra el crédito de almacenamiento).

> **Dos fallos de comando durante la tarea**, los dos por ejecutarlos en la máquina equivocada:
> `agent_control` es del *manager*, no del agente, y `ssh <alias>` desde el laptop sirve para
> lanzar un comando remoto sin abrir sesión. Conviene indicar siempre en qué máquina va cada comando.
