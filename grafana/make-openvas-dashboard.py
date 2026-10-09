#!/usr/bin/env python3
"""Genera el dashboard de Grafana "Vulnerabilidades de red (OpenVAS)".

Uso:  python grafana/make-openvas-dashboard.py [salida.json]
Salida por defecto: grafana/openvas-dashboard.json

Datos: alertas de Wazuh de las reglas 101001-101004 (grupo `openvas`), generadas a partir de
los hallazgos que exporta tools/openvas_to_wazuh.py. Campos usados: data.cliente, data.host,
data.puerto, data.severidad, data.cvss, data.nombre, data.solucion.

Portable: la fuente de datos es una VARIABLE de Grafana (${ds}, tipo datasource). Se elige en
el desplegable del propio dashboard, así el mismo JSON sirve para el lab, la demo y producción.

Selector de cliente ($cliente, texto): "*" = todos; "c001-*" = solo ese cliente. Se compara con
data.cliente, que sale del nombre de la tarea de Greenbone (`scan-<cliente>`). Si las tareas se
nombran igual que los agentes de Wazuh, el mismo patrón sirve en todos los dashboards.
Es una comodidad del operador, NO una barrera de seguridad entre clientes.

Nota: cada exportación de un informe añade sus hallazgos como alertas nuevas, así que un
reescaneo vuelve a contar los hallazgos que siguen abiertos. El rango de tiempo del dashboard
decide qué escaneos se muestran.
"""
import json
import sys
from pathlib import Path

SALIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "openvas-dashboard.json"

DS = {"type": "grafana-opensearch-datasource", "uid": "${ds}"}
BASE = "rule.groups:openvas AND data.cliente:${cliente:raw}"
COLORES = {"Critical": "#F2495C", "High": "#FF780A", "Medium": "#FADE2A", "Low": "#5794F2"}
ES = {"Critical": "Crítica", "High": "Alta", "Medium": "Media", "Low": "Baja"}
THRESH = {"mode": "absolute", "steps": [{"color": "green", "value": 0}, {"color": "red", "value": 80}]}


def target(query, bucket_aggs=None, metrics=None):
    return {
        "alias": "",
        "bucketAggs": bucket_aggs if bucket_aggs is not None else [],
        "datasource": DS,
        "metrics": metrics or [{"id": "1", "type": "count"}],
        "query": query,
        "queryType": "lucene",
        "refId": "A",
        "timeField": "timestamp",
    }


def terms(field, size="10", id_="2"):
    return {"field": field, "id": id_, "type": "terms",
            "settings": {"min_doc_count": "1", "order": "desc", "orderBy": "_count", "size": size}}


def histo(id_="2"):
    return {"field": "timestamp", "id": id_, "type": "date_histogram",
            "settings": {"interval": "auto", "min_doc_count": "0", "trimEdges": "0"}}


def stat(id_, titulo, query, x, w, color, desc=""):
    return {
        "id": id_, "type": "stat", "title": titulo, "description": desc, "datasource": DS,
        "gridPos": {"h": 4, "w": w, "x": x, "y": 0},
        "fieldConfig": {"defaults": {"color": {"fixedColor": color, "mode": "fixed"}, "decimals": 0,
                                     "noValue": "0", "thresholds": THRESH, "unit": "short"}, "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "center",
                    "orientation": "auto", "percentChangeColorMode": "standard",
                    "reduceOptions": {"calcs": ["sum"], "fields": "", "values": False},
                    "showPercentChange": False, "textMode": "value", "wideLayout": True},
        "targets": [target(query, [histo()])],
    }


def sev(nivel):
    return BASE + ' AND data.severidad:"%s"' % nivel


def colores_por_nombre(nombres, traducir=False):
    """Color fijo por nombre de serie; con traducir=True además muestra el nombre en español."""
    out = []
    for n, c in nombres:
        props = [{"id": "color", "value": {"fixedColor": c, "mode": "fixed"}}]
        if traducir and n in ES:
            props.append({"id": "displayName", "value": ES[n]})
        out.append({"matcher": {"id": "byName", "options": n}, "properties": props})
    return out


def panel_tiempo():
    filtros = [{"label": ES[k], "query": 'data.severidad:"%s"' % k} for k in COLORES]
    return {
        "id": 6, "type": "timeseries", "title": "Hallazgos en el tiempo por severidad", "datasource": DS,
        "description": "Hallazgos detectados en cada escaneo exportado, separados por severidad.",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 4},
        "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"},
                                     "custom": {"drawStyle": "bars", "fillOpacity": 80, "lineWidth": 1,
                                                "showPoints": "never", "stacking": {"group": "A", "mode": "normal"},
                                                "barAlignment": 0, "barWidthFactor": 0.6},
                                     "thresholds": THRESH},
                        "overrides": colores_por_nombre([(ES[k], c) for k, c in COLORES.items()])},
        "options": {"legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": True},
                    "tooltip": {"hideZeros": False, "mode": "multi", "sort": "desc"}},
        "targets": [target(BASE, [{"id": "3", "type": "filters", "settings": {"filters": filtros}}, histo("4")])],
    }


def panel_pie():
    return {
        "id": 7, "type": "piechart", "title": "Reparto por severidad", "datasource": DS,
        "gridPos": {"h": 8, "w": 6, "x": 0, "y": 12},
        "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}, "custom": {"hideFrom": {"legend": False, "tooltip": False, "viz": False}}},
                        "overrides": colores_por_nombre(list(COLORES.items()), traducir=True)},
        "options": {"displayLabels": ["percent"], "legend": {"displayMode": "table", "placement": "right", "showLegend": True, "values": ["value"]},
                    "pieType": "donut", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                    "sort": "desc", "tooltip": {"hideZeros": False, "mode": "single", "sort": "none"}},
        "targets": [target(BASE, [terms("data.severidad", "5")])],
    }


def panel_barras(id_, titulo, campo, x, w, color, desc):
    return {
        "id": id_, "type": "barchart", "title": titulo, "description": desc, "datasource": DS,
        "gridPos": {"h": 8, "w": w, "x": x, "y": 12},
        "fieldConfig": {"defaults": {"color": {"fixedColor": color, "mode": "fixed"},
                                     "custom": {"axisPlacement": "auto", "fillOpacity": 80, "gradientMode": "none",
                                                "hideFrom": {"legend": False, "tooltip": False, "viz": False},
                                                "lineWidth": 1, "scaleDistribution": {"type": "linear"}},
                                     "thresholds": THRESH}, "overrides": []},
        "options": {"barRadius": 0, "barWidth": 0.97, "fullHighlight": False, "groupWidth": 0.7,
                    "legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": False},
                    "orientation": "horizontal", "showValue": "auto", "stacking": "none",
                    "tooltip": {"hideZeros": False, "mode": "single", "sort": "none"},
                    "xTickLabelMaxLength": 70, "xTickLabelRotation": 0, "xTickLabelSpacing": 0},
        "targets": [target(BASE, [terms(campo)])],
    }


def panel_tabla():
    mapeo = {k: {"color": c, "index": i, "text": ES[k]} for i, (k, c) in enumerate(COLORES.items())}
    return {
        "id": 10, "type": "table", "title": "Detalle de hallazgos", "datasource": DS,
        "description": "Los 100 hallazgos más recientes con su solución recomendada.",
        "gridPos": {"h": 11, "w": 24, "x": 0, "y": 20},
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "inspect": False},
                                     "thresholds": THRESH},
                        "overrides": [
                            {"matcher": {"id": "byName", "options": "Severidad"},
                             "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background"}},
                                            {"id": "mappings", "value": [{"type": "value", "options": mapeo}]},
                                            {"id": "custom.width", "value": 110}]},
                            {"matcher": {"id": "byName", "options": "CVSS"}, "properties": [{"id": "custom.width", "value": 70}, {"id": "decimals", "value": 1}]},
                            {"matcher": {"id": "byName", "options": "Solución"}, "properties": [{"id": "custom.width", "value": 420}]}]},
        "options": {"cellHeight": "sm", "showHeader": True, "sortBy": [{"desc": True, "displayName": "Hora"}]},
        "targets": [target(BASE, [], [{"id": "1", "type": "raw_data", "settings": {"size": "100"}}])],
        "transformations": [
            {"id": "filterFieldsByName", "options": {"include": {"names": [
                "timestamp", "data.cliente", "data.host", "data.puerto", "data.severidad", "data.cvss", "data.nombre", "data.solucion"]}}},
            {"id": "organize", "options": {
                "indexByName": {"timestamp": 0, "data.cliente": 1, "data.host": 2, "data.puerto": 3, "data.severidad": 4,
                                "data.cvss": 5, "data.nombre": 6, "data.solucion": 7},
                "renameByName": {"timestamp": "Hora", "data.cliente": "Cliente", "data.host": "Equipo", "data.puerto": "Puerto",
                                 "data.severidad": "Severidad", "data.cvss": "CVSS", "data.nombre": "Vulnerabilidad",
                                 "data.solucion": "Solución"}}}],
    }


def main():
    paneles = [
        stat(1, "Hallazgos totales", BASE, 0, 4, "#73BF69", "Vulnerabilidades encontradas por OpenVAS en el rango de tiempo."),
        stat(2, "Críticos", sev("Critical"), 4, 5, COLORES["Critical"], "Los que disparan aviso por Telegram (regla de nivel 12)."),
        stat(3, "Altos", sev("High"), 9, 5, COLORES["High"]),
        stat(4, "Medios", sev("Medium"), 14, 5, "#FF9830"),
        stat(5, "Bajos", sev("Low"), 19, 5, COLORES["Low"]),
        panel_tiempo(),
        panel_pie(),
        panel_barras(8, "Hallazgos por cliente", "data.cliente", 6, 5, "#5794F2", "Cuántos hallazgos tiene cada cliente."),
        panel_barras(9, "Vulnerabilidades más frecuentes", "data.nombre", 11, 13, "#B877D9", "Las 10 vulnerabilidades que más se repiten."),
        panel_tabla(),
    ]
    dash = {
        "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                                  "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
                                  "name": "Annotations & Alerts", "type": "dashboard"}]},
        "description": "Vulnerabilidades de red detectadas por OpenVAS (Greenbone). Selector de cliente: * = todos.",
        "editable": True, "fiscalYearStartMonth": 0, "graphTooltip": 1, "id": None, "links": [], "liveNow": False,
        "panels": paneles, "refresh": "5m", "schemaVersion": 42,
        "tags": ["wazuh", "openvas", "vulnerabilidades"],
        "templating": {"list": [
            {"name": "ds", "label": "Fuente de datos", "type": "datasource", "query": "grafana-opensearch-datasource",
             "regex": "/^(?!.*(Vulnerab|vuln)).*$/", "refresh": 1, "hide": 0, "current": {}, "options": []},
            {"name": "cliente", "label": "Cliente (* = todos; c001-* = uno)", "type": "textbox", "query": "*",
             "current": {"text": "*", "value": "*"}, "options": [{"selected": True, "text": "*", "value": "*"}], "hide": 0}]},
        "time": {"from": "now-7d", "to": "now"},
        "timepicker": {"refresh_intervals": ["30s", "1m", "5m", "15m", "30m", "1h", "1d"]},
        "timezone": "browser", "title": "Vulnerabilidades de red (OpenVAS)", "uid": "openvas-vulnerabilidades",
        "version": 1, "weekStart": "",
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(dash, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("escrito %s (%d paneles)" % (SALIDA, len(paneles)))


if __name__ == "__main__":
    main()
