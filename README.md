# openvas-homelab

Reconstrucción documentada, paso a paso, de un servidor **Greenbone Community Edition
(OpenVAS)** sobre una VM en la nube, accesible solo por VPN, con sus hallazgos integrados en
**Wazuh** y visualizados en **Grafana**. Parte de un servicio de ciberseguridad para
microempresas.

> Cada fase documenta los comandos, la verificación, cómo revertir y los fallos reales
> encontrados. El historial de commits sigue el orden en que se hizo el trabajo.

## Arquitectura

```
 Laptop admin ──Tailscale──► soc-openvas-01 (Greenbone en Docker Compose)
                                   │  tools/openvas_to_wazuh.py  (JSON, un hallazgo por línea)
                                   ▼
                          agente Wazuh ──► Wazuh Manager (reglas 101001-101004)
                                                   │
                                                   ▼
                                       OpenSearch ──► Grafana
```

- Gestión únicamente por Tailscale; ninguna interfaz expuesta a internet.
- Greenbone ve la red desde fuera (puertos, servicios, TLS); Wazuh ve el software instalado
  mediante agente. Juntos dan cobertura interna y externa.
- El escáner solo lee de Greenbone; no crea ni modifica nada en gvmd.

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| [0](docs/00-metodo.md) | Método de trabajo y reglas | ✅ |
| [A](docs/01-fase-a-vm-infomaniak.md) | VM en Infomaniak, Tailscale, UFW | ✅ |
| [B](docs/02-fase-b-docker-greenbone.md) | Docker, Greenbone, feeds y dos escaneos | ✅ |
| [C](docs/03-fase-c-integracion-wazuh.md) | Exportador, reglas y agente Wazuh | ✅ |
| [D](docs/04-fase-d-dashboard-grafana.md) | Dashboard de Grafana | ✅ validado con datos reales |
| [E](docs/05-fase-e-unificacion-demo.md) | Unificación con los dashboards de Wazuh y paso a demo | 🔄 |

## Contenido

- `docs/` — diario por fase.
- `tools/openvas_to_wazuh.py` — exportador de hallazgos (solo lectura sobre Greenbone).
- `wazuh/` — reglas del manager y fragmento de configuración del agente.
- `grafana/` — generador y JSON del dashboard.

## Seguridad del repositorio

No contiene credenciales, claves, IPs públicas ni resultados de escaneos reales.
Los valores sensibles se sustituyen por marcadores como `<IP_TAILSCALE>`.
