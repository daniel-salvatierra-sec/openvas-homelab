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

## 2026-10-12 · Actualización del feed, cuelgue de la VM y swap

**Hallazgo:** tras el reinicio, *Administration → Feed Status* mostraba las cuatro filas como
`4 days old` (versión del 8 de octubre). Según la documentación oficial, los contenedores de
datos **copian a los volúmenes el feed que viene dentro de su imagen cada vez que arrancan**;
no se sincronizan solos. Para actualizar el feed hay que descargar imágenes nuevas y
recrear los contenedores de datos:

```bash
df -h /; docker system df                                  # comprobar espacio antes (imágenes + volúmenes)
docker compose -f ~/greenbone-community-edition/compose.yaml pull
docker compose -f ~/greenbone-community-edition/compose.yaml up -d
```

Sin `down`, sin `-v` y sin `prune`. Tras el `up -d`, `gvmd` recarga la caché de VTs
(**45-50 minutos**, con *Update in progress* en *Feed Status*). Resultado: las cuatro filas en
**Current** con versión del día.

**Incidente:** durante el primer `up -d`, mientras `vulnerability-tests` copiaba sus datos, se
cortó la sesión SSH y la VM dejó de responder por Tailscale (el nodo apareció desconectado).
Según Infomaniak la instancia seguía *Active* y *En fonctionnement*. El log de consola
(*Journal*) solo contenía el arranque de esa mañana, sin `Out of memory` ni pánico del kernel.
**La causa no se confirmó**; la hipótesis de trabajo fue saturación de memoria o de disco (8 GB de
RAM y **sin swap**) durante una copia de ~38 GB. No había otra vía de acceso: el SSH público
está cerrado en el grupo de seguridad y en UFW, y no hay contraseña de usuario para la consola.

**Recuperación:** reinicio **suave** desde el panel (*Redémarrer l'instance*), nunca el
forzado (*matériellement*), y menos aún *Reconstruire* o *Supprimer*. Antes se verificó en cuál
de las máquinas estaba abierto el menú. Tras volver, los contenedores de datos no arrancan solos
(política `no`) y se repitió el `up -d`, esta vez dentro de `tmux`.

**Medidas para que no se repita:**

- **Swap de 2 GB**, con copia de `fstab` antes de tocarlo:

```bash
sudo cp /etc/fstab /etc/fstab.bak-AAAAMMDD
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

  Revertir: `sudo swapoff /swapfile && sudo rm /swapfile` y restaurar `fstab`.
- **Operaciones largas dentro de `tmux`** (`tmux new -s feeds`; separar con `Ctrl+b d`;
  volver con `tmux attach -t feeds`), para que un corte de SSH no las interrumpa.
- Vigilar el disco: pasó de 28 GB a 14 GB libres durante la actualización, porque las imágenes
  viejas conviven con las nuevas hasta limpiarlas.

**Dos de los fallos fueron de método:** lanzar comandos del *manager* en la VM del agente y
pegar marcadores sin sustituir. Conviene nombrar siempre la máquina de cada comando.
