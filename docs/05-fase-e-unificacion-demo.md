# Fase E — Unificación con los dashboards de Wazuh y paso al entorno de demo

Fecha: 2026-10-09 · Estado: **en curso** (datos verificados en el manager de demo; falta validar el dashboard)

## E1 · Una sección de OpenVAS dentro de los dashboards del proyecto

Los dashboards de operación (producción) y de demo ya reúnen las alertas de Wazuh y sus
vulnerabilidades. Unificar es añadirles una sección final, **Vulnerabilidades de red (OpenVAS)**,
con los 10 paneles de la fase D, el mismo selector de cliente y el datasource de alertas de
cada entorno. Los generadores del proyecto toman el JSON de OpenVAS como entrada; los paneles
que ya existían quedan intactos (se comprobó panel a panel) y no hay IDs duplicados.

## E2 · Por qué hubo que mover el agente

Un dashboard solo ve el OpenSearch de **su** manager. El agente del escáner reportaba al manager
del laboratorio, así que la sección habría salido vacía en demo y producción. Como lo que se
escanea son los equipos de la demo, el agente pasa al manager de demo. Para clientes reales se
repetirá hacia el manager de producción (nunca mezclar laboratorio y clientes).

## E3 · Convención de nombres

El selector de cliente de la demo filtra por `c900-*` / `c901-*`, que son los nombres de sus
agentes. El campo `cliente` de los hallazgos sale del nombre de la tarea de Greenbone, así que
las tareas se nombran `scan-<nombre del agente>`: `scan-c901-etude-secretariat`. Renombrar una
tarea basta: los informes ya hechos toman el nombre nuevo.

## E4 · Mover el agente al manager de demo

Con copia con fecha de `client.keys` y `ossec.conf` antes de cada cambio.

1. Reglas `openvas_rules.xml` (101000-101004, libres) en el manager de demo, comprobación de
   sintaxis y reinicio. La versión del manager coincide con la del agente (4.14.8).
2. En la VM del escáner: parar el agente, cambiar `<address>`, vaciar `client.keys` y arrancar.

> **Lo que falló:** `ERROR: Invalid password. Unable to add agent (from manager)`. El manager de
> demo exige contraseña de enrolamiento (el del laboratorio no). Se copió el contenido de su
> `etc/authd.pass` con el portapapeles y se guardó en el agente con `read -s`, sin pasar por el
> historial ni por ningún chat.

3. Los hallazgos se reexportaron desde cero: `results.json` y `processed_reports.txt` se
   apartaron con copia con fecha y se crearon vacíos, de modo que la exportación vuelve a
   procesar los informes con el nombre de cliente nuevo.

```bash
cd /var/log/openvas
sudo mv results.json results.json.bak-AAAAMMDD && sudo mv processed_reports.txt processed_reports.txt.bak-AAAAMMDD
sudo touch results.json processed_reports.txt && sudo chown 1001:1001 results.json processed_reports.txt
sudo systemctl restart wazuh-agent
```

Verificado: dos alertas de la regla 101001 en el manager de demo, agente `soc-openvas-01`.

## Pendiente

- Importar el dashboard de demo regenerado y validar la sección de OpenVAS con `c901-*`.
- Limpiar el agente antiguo del manager del laboratorio (quedó desconectado).
- Equivalente para producción cuando haya clientes reales: agente propio hacia el manager de
  producción y los informes en PDF mensuales.
