# Fase E — Unificación con los dashboards de Wazuh y paso al entorno de demo

Fecha: 2026-10-09 · Estado: **completada para el entorno de demo**

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

## E5 · Despliegue en el Grafana de demo

El dashboard de demo se despliega por *file provisioning* (JSON en `/var/lib/grafana/dashboards/`,
propiedad de `grafana`, modo 640; Grafana lo relee solo en ~30 s), con copia con fecha del anterior.

> **Lo que falló:** el primer intento fue importar el JSON desde la interfaz del Grafana del
> **laboratorio**. Salió todo vacío porque el dashboard de demo usa el datasource `wazuh-demo-alerts`,
> que solo existe en el Grafana del servidor de demo. Un dashboard solo ve las fuentes de datos de
> su propio Grafana. Se borró el importado por error y se desplegó en el servidor correcto.

Resultado: la sección **Vulnerabilidades de red (OpenVAS)** muestra los 2 hallazgos Low del
equipo de la demo.

## E6 · El escáner no es un cliente

Como agente del manager de demo, `soc-openvas-01` aparecía en "Agentes que reportaron", "Alertas
por agente" y en la tabla de vulnerabilidades críticas de Wazuh (con los CVE del kernel de la
propia VM). En una demo eso enseñaría infraestructura del operador como si fuera de un cliente.
Los generadores de dashboards excluyen ahora `agent.name:"soc-openvas-01"` de todos los paneles
de Wazuh; los de la sección OpenVAS no llevan esa exclusión.

## Pendiente

- Comprobar el selector de cliente de la demo: `c901-*` debe dejar 2 hallazgos y `c900-*` ninguno.
- Revisar los CVE del kernel de la propia VM del escáner (actualizar y reiniciar si procede).
- Limpiar el agente antiguo del manager del laboratorio (quedó desconectado).
- Equivalente para producción cuando haya clientes reales: agente propio hacia el manager de
  producción y los informes en PDF mensuales.
