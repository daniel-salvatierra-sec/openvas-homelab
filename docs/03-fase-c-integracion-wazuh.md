# Fase C — Integración con Wazuh (hallazgos → Wazuh → Grafana)

Fecha de inicio: 2026-10-09 · Estado: **en curso**

## Decisión de diseño

Dos opciones para llevar los datos de Greenbone a Grafana:

| | A. Grafana lee PostgreSQL de Greenbone | B. Exportar a Wazuh/OpenSearch (elegida) |
|---|---|---|
| Cómo | Dashboard comunitario conectado a la base `gvmd` | Script `python-gvm` escribe un JSON por hallazgo, Wazuh lo indexa |
| Seguridad | Hay que exponer Postgres a otra VM | No se abre ninguna base de datos |
| Grafana | Una fuente de datos nueva | La misma que ya usan los demás dashboards |
| Por cliente | Difícil de aislar | Campo `cliente` en cada hallazgo |
| Alertas | No | Reutiliza la cadena de alertas existente |

Se elige **B**: un único origen de datos, ninguna base de datos expuesta y filtrado por
cliente desde el principio.

## C1 · Exportador `tools/openvas_to_wazuh.py`

Se ejecuta **dentro del contenedor `gvm-tools`** (trae `python-gvm` y acceso al socket de
gvmd), sin modificar el compose. Solo lectura sobre Greenbone. La contraseña llega por
variable de entorno, nunca por argumento ni en el repo.

- Una línea JSON por hallazgo en `/var/log/openvas/results.json`.
- Solo informes con estado `Done`; los ya exportados se registran en `processed_reports.txt`
  (sin duplicados).
- `--dry-run` imprime sin escribir. Por defecto se omiten los resultados de severidad 0
  (tipo *Log*); `--include-log` los incluye.
- El campo `cliente` sale del nombre de la tarea (`scan-<cliente>`).

Prueba con `--dry-run` sobre los dos informes reales (`scan-prueba-self`: 4 resultados Log;
`scan-demo-pc02`: 12 resultados, 2 de ellos Low). Funcionó a la primera.

```bash
read -rsp "Contraseña admin: " GVM_PASSWORD; echo; export GVM_PASSWORD GVM_USER=admin
docker compose -f $HOME/greenbone-community-edition/compose.yaml run --rm \
  -e GVM_USER -e GVM_PASSWORD -v $HOME/openvas-export/tools:/tools:ro \
  gvm-tools python3 /tools/openvas_to_wazuh.py --dry-run
unset GVM_PASSWORD
```

## C2 · Reglas en el manager `wazuh/openvas_rules.xml`

Archivo **nuevo** (no se modifica ninguna regla existente), rango reservado `101000-101009`
tras comprobar los IDs ocupados (los de 100000 a 100432 estaban en uso).

| Severidad | Regla | Nivel | Aviso a Telegram (≥ 10) |
|---|---|---|---|
| Low | 101001 | 3 | no |
| Medium | 101002 | 6 | no |
| High | 101003 | 9 | no |
| Critical | 101004 | 12 | sí |

Wazuh solo indexa los eventos que disparan una regla, por eso sin reglas los hallazgos
nunca llegarían a OpenSearch ni a Grafana.

Validación sin reiniciar:

```bash
sudo /var/ossec/bin/wazuh-analysisd -t && echo SINTAXIS_OK
echo '<línea JSON de prueba>' | sudo /var/ossec/bin/wazuh-logtest -U 101001:3:json
```

> **Lo que falló:** con `wazuh-logtest -q` en modo no interactivo no se imprime nada. El modo
> de aserción `-U <regla>:<nivel>:<decoder>` sí lo comprueba (`Unit test OK`, código 0).

Resultado: la regla 101001 dispara con nivel 3.

**Cómo revertir:** `sudo rm /var/ossec/etc/rules/openvas_rules.xml` y reiniciar el manager.

## C3 · Agente Wazuh en la VM de OpenVAS

Versión igual a la del manager (4.14.8); el agente nunca debe ser más nuevo que el manager.

```bash
curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH | sudo gpg --no-default-keyring \
  --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import
echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" \
  | sudo tee /etc/apt/sources.list.d/wazuh.list && sudo apt update
sudo WAZUH_MANAGER="<IP_TAILSCALE_MANAGER>" WAZUH_AGENT_NAME="soc-openvas-01" \
  apt install -y wazuh-agent=4.14.8-1
```

Se instala **sin arrancar**, se hace copia con fecha de `ossec.conf` y se añade el bloque
`wazuh/agent-localfile.xml` (formato `json`, archivo `/var/log/openvas/results.json`) justo
antes del último `</ossec_config>`. Luego `systemctl enable --now wazuh-agent`.

El manager no usa contraseña de enrolamiento (no existe `authd.pass`), así que el agente
se registra solo. Verificado en el log: `Valid key received` y `Connected to the server`
por el puerto 1514. En el manager, `agent_control -l` lo lista como `Active` (ID 008).

> **Nota:** `agent_control` es una herramienta del manager, no existe en el agente.

## Pendiente

- Reiniciar el manager para cargar las reglas
- Ejecutar el exportador de verdad y comprobar el alerta en Wazuh
- Paneles de Grafana sobre el índice `wazuh-alerts-*` (campos `data.cliente`, `data.severidad`…)
- Decidir qué hacer con los hallazgos de la demo (dejarlos para el dashboard)
