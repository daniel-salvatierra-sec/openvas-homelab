# Método de trabajo

Cada fase de este proyecto sigue las mismas reglas:

1. **Un comando por paso.** No se avanza sin verificar la salida del anterior.
2. **Solo lectura primero.** Se observa el estado real antes de modificar nada.
3. **Copia con fecha** (`archivo.bak-AAAAMMDD`) antes de editar cualquier archivo existente.
4. **Nada destructivo.** Prohibido `rm -r`, `docker compose down -v`, `docker volume rm` y `DROP`.
5. **Verificar antes de declarar éxito:** servicio activo, puerto accesible, log limpio.
6. **Acceso de administración solo por VPN (Tailscale).** Ninguna interfaz expuesta a internet.
7. **Sin secretos en el repositorio.** Contraseñas, claves y IPs públicas no se publican.

## Contexto

Este repositorio documenta la reconstrucción de un servidor Greenbone Community Edition
(OpenVAS) para auditar infraestructura propia, como parte de un servicio de ciberseguridad
para microempresas. La instalación anterior se perdió al eliminarse su máquina virtual;
esta vez se reconstruye paso a paso, con snapshots y todo versionado en Git.

Nomenclatura de los comandos: cada bloque indica dónde se ejecuta
(`[Laptop · PowerShell]` o `[VM soc-openvas-01]`).
