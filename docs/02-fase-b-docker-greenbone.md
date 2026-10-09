# Fase B — Docker y Greenbone Community Containers

Fecha de inicio: 2026-10-08 · Estado: **en curso**

Guía seguida: documentación oficial *Greenbone Community Containers*
(https://greenbone.github.io/docs/latest/22.4/container/index.html), verificada el día de la
instalación. La propia guía indica que es una instalación para pruebas y aprendizaje, no un
despliegue de producción; aquí se endurece con acceso solo por VPN.

## B1 · Docker Engine `[VM]`

```bash
curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
sudo docker --version && sudo docker compose version
```

Resultado: Docker 29.8.2, Compose v5.6.0. Se usó el script oficial de Docker, que configura
su repositorio apt (no el paquete antiguo `docker.io`).

## B2 · Acceso sin sudo `[VM]`

```bash
sudo usermod -aG docker ubuntu
# cerrar sesión y volver a entrar
docker ps
```

## B3 · Descargar el compose oficial `[VM]`

```bash
export DOWNLOAD_DIR=$HOME/greenbone-community-edition && mkdir -p $DOWNLOAD_DIR
curl -f -O -L https://greenbone.github.io/docs/latest/_static/compose.yaml --output-dir "$DOWNLOAD_DIR"
grep -n "127.0.0.1\|ports:" $DOWNLOAD_DIR/compose.yaml
```

**Revisión de seguridad antes de arrancar:** el único servicio con puertos publicados es
`nginx`, enlazado a `127.0.0.1:443` y `127.0.0.1:9392`. El puerto de `openvasd` viene
comentado. Nada queda expuesto fuera de la VM; el acceso web será por túnel SSH sobre Tailscale.

## B4 · Copia con fecha y descarga de imágenes `[VM]`

```bash
cp $DOWNLOAD_DIR/compose.yaml $DOWNLOAD_DIR/compose.yaml.bak-20261008
docker compose -f $DOWNLOAD_DIR/compose.yaml pull
```

Las 19 imágenes se descargaron sin errores (el tiempo por imagen fue de 50 s a 533 s).

## B5 · Arrancar el stack `[VM]`

```bash
docker compose -f $DOWNLOAD_DIR/compose.yaml up -d
docker compose -f $DOWNLOAD_DIR/compose.yaml ps --format "table {{.Service}}\t{{.Status}}"
```

Los 16 servicios en ejecución; `gvmd`, `pg-gvm`, `gsa` y los de datos en estado `healthy`.
Los feeds CERT-Bund y DFN-CERT se sincronizaron primero; la base SCAP (`nvd-cpe-matches.json.gz`)
es la parte larga. Mientras tanto `gvmd` registra `No SCAP database found`, que es normal.

## B6 · Contraseña de `admin` `[VM]`

La instalación crea `admin/admin`, que es inseguro. Se cambia sin dejar la contraseña en el
historial de la shell:

```bash
read -rsp "Nueva contraseña admin: " P; echo
docker compose -f $DOWNLOAD_DIR/compose.yaml exec -u gvmd gvmd gvmd --user=admin --new-password="$P"; unset P
```

> **Lo que falló:** la primera vez se copió el comando con el marcador `TU_CONTRASEÑA` sin
> sustituirlo, por lo que la contraseña real quedó con ese texto. Se repitió con `read -s`.
> Lección: la contraseña nunca se escribe en el comando; se guarda en el gestor de contraseñas.

## B7 · Acceso a la interfaz por túnel SSH `[Laptop · PowerShell]`

La interfaz solo escucha en `127.0.0.1` dentro de la VM. Se accede con un túnel por Tailscale:

```powershell
ssh -i "$HOME\.ssh\infomaniak_openvas_rsa" -L 8443:127.0.0.1:443 ubuntu@<IP_TAILSCALE>
```

Navegador: `https://127.0.0.1:8443/` (certificado autofirmado: se acepta la excepción).
Se entra desde la raíz `/`; la interfaz es una SPA y `/login` no existe como ruta.

Resultado: acceso correcto con el usuario `admin`.

## B8 · Comprobar el estado de los feeds `[Interfaz web]`

*Administration → Feed Status*: NVT, SCAP, CERT y GVMD_DATA en **Current** (versión del
2026-10-08). Hasta que los cuatro están en Current no se lanzan escaneos.

## B9 · Snapshot `openvas-operativo` `[Panel Infomaniak]`

Punto de restauración con el stack funcionando y los feeds al día.

## B10 · Escaneo de prueba sobre la propia VM `[Interfaz web]`

Objetivo: validar la cadena completa (target → tarea → informe), no buscar hallazgos.

Target `openvas-self`:
- Host: la IP Tailscale de la VM.
- Port List: `All IANA assigned TCP`.
- Alive Test: `Consider Alive`, porque con UFW activo la VM puede parecer inactiva al test de vida y el escaneo terminaría con 0 hosts.

> **Lo que falló:** el formulario dio `Error in host specification` al pegar la IP. Al
> escribirla a mano y cambiar el nombre a `openvas-self` se guardó. Causa más probable: un
> carácter invisible al copiar y pegar.

Tarea `scan-prueba-self`:
- Scanner: `OpenVAS Default`.
- Scan Config: **Full and fast**. Es el escaneo completo recomendado por Greenbone: ejecuta
  casi todos los NVTs y solo omite los que no aplican según la detección previa. *Full and
  deep* tarda mucho más, casi nunca añade hallazgos y puede afectar a servicios frágiles.
- Add results to Assets: Yes · Apply Overrides: No · Min QoD: 70 · Alterable: No.
- Sin horario (`Once`): es una auditoría puntual, no un servicio continuo.

Expectativa: con UFW denegando todo salvo `tailscale0`, el escáner verá pocos puertos
abiertos. Es esperable.

**Resultado:** estado *Done*, 0 hallazgos Critical/High/Medium/Low, severidad máxima `0.0 (Log)`.
La cadena target → tarea → informe funciona. El resultado vacío es coherente con el firewall,
pero no demuestra que el escáner detecte vulnerabilidades: hace falta un objetivo con servicios
visibles.

## B11 · Segundo escaneo sobre un equipo de la demo

Objetivo: obtener hallazgos reales para el dashboard. Se eligió un equipo propio de la demo
(cliente ficticio), nunca equipos de producción.

El equipo no estaba en la tailnet y su grupo de seguridad solo permitía SSH desde IPs del
administrador, así que se añadió una **regla temporal** de entrada (TCP 1-65535, solo desde la
IP pública de la VM de OpenVAS, `/32`), con descripción `TEMPORAL escaneo OpenVAS - borrar`.

> **Lo que falló:** el formulario dio `Le port spécifié est invalide` al dejar vacío el campo
> *Port*. Para abrir todos los puertos hay que cambiar *Ouvrir* de `Port` a `Plage de ports`
> (1 – 65535).

Al terminar el escaneo, la regla temporal se elimina.

## Decisión de diseño: qué entra en la tailnet

- **Máquinas propias** (demo, servidores): sí, con etiquetas y ACLs (`tag:scanner` solo puede
  iniciar conexiones hacia `tag:demo`, nunca al revés).
- **PCs de clientes reales**: no se unen a la tailnet propia. Alternativas: escaneo externo con
  autorización escrita, sonda en la red del cliente con una tailnet aislada, o detección de
  vulnerabilidades de Wazuh mediante agente.

## Pendiente

- Revisar el informe del segundo escaneo y borrar la regla temporal
- Fase C: exportar resultados y crear el dashboard

## Problemas conocidos de una instalación anterior (a vigilar)

- `gvmd` atascado en *No feed version available yet* tras un reinicio: `docker compose restart gvmd`.
- Redis escucha solo por socket Unix; un *connection refused* en el 6379 es normal.
- Los escaneos lanzados durante la sincronización de feeds pueden agotar el tiempo: esperar a que termine.
