# Fase D — Dashboard de Grafana

Fecha: 2026-10-09 · Estado: **generado, pendiente de importar y validar en Grafana**

## Resultado de la cadena de datos (verificado)

Greenbone → `tools/openvas_to_wazuh.py` → `/var/log/openvas/results.json` → agente Wazuh →
manager (reglas `101001-101004`) → índice de alertas. Comprobado en `alerts.json` del manager:
dos alertas de la regla `101001` (nivel 3) del agente `soc-openvas-01`, con `data.cliente`,
`data.severidad`, `data.host`, `data.puerto`, `data.nombre` y `data.solucion` ya extraídos
por el decoder JSON.

> **Lo que falló en el exportador:** el contenedor `gvm-tools` arranca como root pero su
> entrypoint **cambia al usuario interno `gvm` (UID 1001)**. Con `--user root` el script corría
> como `gvm` y no podía escribir en un archivo de `ubuntu`; con `--user 1000:1000` el cambio de
> usuario no está permitido. Solución: dar a `gvm` los dos archivos de salida:
> `sudo chown 1001:1001 /var/log/openvas/results.json /var/log/openvas/processed_reports.txt`.
> El agente Wazuh corre como root y los lee igualmente.

## D1 · Generador `grafana/make-openvas-dashboard.py`

Genera `grafana/openvas-dashboard.json` (uid `openvas-vulnerabilidades`, 10 paneles),
siguiendo el modelo de los demás dashboards del proyecto:

| Panel | Tipo | Campo |
|---|---|---|
| Hallazgos totales / Críticos / Altos / Medios / Bajos | stat | `data.severidad` |
| Hallazgos en el tiempo por severidad | barras apiladas | `data.severidad` |
| Reparto por severidad | donut | `data.severidad` |
| Hallazgos por cliente | barras | `data.cliente` |
| Vulnerabilidades más frecuentes | barras | `data.nombre` |
| Detalle de hallazgos (con solución) | tabla | varios |

Decisiones:

- **Fuente de datos como variable** (`${ds}`, tipo datasource): el mismo JSON sirve para el
  lab, la demo y producción; se elige en el desplegable.
- **Selector de cliente** (`$cliente`, `*` = todos, `c001-*` = uno) sobre `data.cliente`. Los
  otros dashboards filtran por `agent.name`, pero aquí todos los hallazgos llegan de un único
  agente (el escáner). Si las tareas de Greenbone se llaman `scan-<nombre del agente>`, el
  mismo patrón vale en todos los dashboards. Es una comodidad del operador, no una barrera de
  seguridad entre clientes.
- **Limitación conocida:** un reescaneo vuelve a exportar los hallazgos que siguen abiertos,
  así que cuentan de nuevo. El rango de tiempo decide qué escaneos se ven.

## Pendiente

- Importar el JSON en Grafana y validar paneles con datos reales
- Decidir a qué manager reporta el escáner en el servicio real: hoy está en el manager del lab;
  para clientes debe ir al manager de producción (nunca mezclar lab y clientes). El dashboard
  no cambia: solo la fuente de datos.
- Paneles de cumplimiento y exportación a PDF mensual para el cliente
