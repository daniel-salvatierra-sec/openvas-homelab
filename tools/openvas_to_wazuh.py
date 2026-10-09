#!/usr/bin/env python3
"""Exporta los hallazgos de Greenbone a JSON Lines para que Wazuh los indexe.

Una línea JSON por hallazgo en OUT_FILE. Solo escribe hallazgos de informes
terminados (status Done) que todavía no se hayan exportado (STATE_FILE).

Se ejecuta DENTRO del contenedor gvm-tools (trae python-gvm y el socket de gvmd):

  docker compose -f $DOWNLOAD_DIR/compose.yaml run --rm \
    -e GVM_USER -e GVM_PASSWORD \
    -v /var/log/openvas:/out -v $PWD/tools:/tools:ro \
    gvm-tools python3 /tools/openvas_to_wazuh.py

Credenciales: solo por variables de entorno (GVM_USER, GVM_PASSWORD). Nunca en el repo.
Solo lectura sobre Greenbone: no crea, modifica ni borra nada en gvmd.

Convención de nombres: el cliente se deduce del nombre de la tarea, `scan-<cliente>`
(p. ej. `scan-demo-pc02` -> cliente `demo-pc02`).

Opciones:
  --dry-run      imprime las líneas por pantalla y no escribe ni marca informes como procesados.
  --include-log  incluye también los resultados informativos (severidad 0, tipo Log).
                 Por defecto se omiten: no son vulnerabilidades y solo añaden ruido en Wazuh.
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

SOCKET_PATH = os.environ.get("GVM_SOCKET", "/run/gvmd/gvmd.sock")
OUT_FILE = os.environ.get("OUT_FILE", "/out/results.json")
STATE_FILE = os.environ.get("STATE_FILE", "/out/processed_reports.txt")
REPORT_FILTER = "apply_overrides=0 min_qod=70 levels=chmlg rows=-1 first=1"


def as_element(resp):
    """python-gvm devuelve un Element o un str según la versión; normaliza."""
    if isinstance(resp, (str, bytes)):
        return ET.fromstring(resp)
    return resp


def tag_value(tags, key):
    """Los NVT guardan tags como 'clave=valor|clave=valor'."""
    for part in (tags or "").split("|"):
        if part.startswith(key + "="):
            return part[len(key) + 1:]
    return ""


def client_from_task(task_name):
    name = task_name or "desconocido"
    return name[5:] if name.startswith("scan-") else name


def parse_results(report_xml, report_id, task_name, report_time, include_log=False):
    """Convierte un <report> de GMP en una lista de dicts, uno por hallazgo."""
    findings = []
    for res in report_xml.iter("result"):
        nvt = res.find("nvt")
        if nvt is None:
            continue
        host_el = res.find("host")
        host = (host_el.text or "").strip() if host_el is not None else ""
        cves = sorted({r.get("id") for r in nvt.iter("ref")
                       if (r.get("type") or "").lower() == "cve" and r.get("id")})
        if not include_log and float(res.findtext("severity") or 0.0) <= 0.0:
            continue
        findings.append({
            "timestamp": report_time,
            "source": "openvas",
            "cliente": client_from_task(task_name),
            "tarea": task_name,
            "report_id": report_id,
            "host": host,
            "puerto": (res.findtext("port") or "").strip(),
            "nvt_oid": nvt.get("oid", ""),
            "nombre": (nvt.findtext("name") or res.findtext("name") or "").strip(),
            "cvss": float(res.findtext("severity") or 0.0),
            "severidad": (res.findtext("threat") or "").strip(),
            "qod": int(res.findtext("qod/value") or 0),
            "cve": cves,
            "solucion": " ".join(tag_value(nvt.findtext("tags"), "solution").split())[:600],
        })
    return findings


def load_processed():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return {line.strip() for line in fh if line.strip()}
    except FileNotFoundError:
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-log", action="store_true")
    args = ap.parse_args()

    user = os.environ.get("GVM_USER", "admin")
    password = os.environ.get("GVM_PASSWORD")
    if not password:
        sys.exit("Falta GVM_PASSWORD en el entorno (no se acepta por argumento).")

    from gvm.connections import UnixSocketConnection
    from gvm.protocols.gmp import Gmp

    processed = load_processed()
    new_lines, new_reports = [], []

    with Gmp(connection=UnixSocketConnection(path=SOCKET_PATH)) as gmp:
        gmp.authenticate(user, password)
        reports = as_element(gmp.get_reports(details=False))
        for rep in reports.iter("report"):
            rid = rep.get("id")
            if not rid or rid in processed:
                continue
            # El <report> externo de get_reports es un contenedor; el interno lleva los datos.
            inner = rep.find("report")
            if inner is None:
                continue
            status = (inner.findtext("scan_run_status") or "").strip()
            if status != "Done":
                continue
            task = inner.find("task")
            task_name = (task.findtext("name") if task is not None else "") or ""
            report_time = (inner.findtext("timestamp")
                           or datetime.now(timezone.utc).isoformat())
            full = as_element(gmp.get_report(
                rid, filter_string=REPORT_FILTER, ignore_pagination=True, details=True))
            findings = parse_results(full, rid, task_name, report_time, args.include_log)
            new_lines.extend(json.dumps(f, ensure_ascii=False) for f in findings)
            new_reports.append(rid)
            print(f"informe {rid} ({task_name}): {len(findings)} hallazgos", file=sys.stderr)

    if args.dry_run:
        print("\n".join(new_lines))
        return
    if new_lines:
        with open(OUT_FILE, "a", encoding="utf-8") as fh:
            fh.write("\n".join(new_lines) + "\n")
    if new_reports:
        with open(STATE_FILE, "a", encoding="utf-8") as fh:
            fh.write("\n".join(new_reports) + "\n")
    print(f"{len(new_lines)} líneas nuevas, {len(new_reports)} informes procesados",
          file=sys.stderr)


if __name__ == "__main__":
    main()
