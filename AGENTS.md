# Reglas de trabajo del proyecto

## Lee primero
1. `docs/ESTADO-VERIFICADO.md` (no repetir como hechos las afirmaciones antiguas del chat).
2. `docs/CONTEXTO-PRODUCTO.md`.
3. `docs/ACEPTACION.md` y `CODEX_PROMPT.md`.

## Objetivo
Completar, ejecutar, probar y entregar una aplicación Windows local para un solo taller.
El trabajo diario debe ser: buscar nombre/matrícula -> factura -> imprimir.
Presupuestos, órdenes, stock y agenda son opcionales y no bloquean ese flujo.
Responde al usuario en castellano. No basta con proponer otro plan.

## Arquitectura y límites
- Conservar React + TypeScript + Tauri 2 + servicio Python + SQLite salvo necesidad demostrada.
- No añadir Supabase, Vercel, autenticación cloud, telemetría o suscripciones para el núcleo.
- No convertir el proyecto en una mera web en localhost como entrega final.
- Usar rutas de datos persistentes del usuario, no la carpeta del ejecutable.
- Proteger borradores, snapshots, numeración, importaciones y copias. No modificar datos reales.
- No insertar datos reales, certificados, claves privadas, `.env` ni bases en Git.
- `private-reference/` contiene datos personales de fotos aportadas por el usuario: lectura local
  para comprender el proyecto; nunca publicación ni envío a servicios externos.
- No crear repositorios remotos, desplegar ni gastar dinero sin autorización explícita.

## Facturación
- VERI*FACTU no equivale a factura electrónica B2B. Separar adaptadores y estado real de cada uno.
- No cambiar un flag de producción para aparentar cumplimiento ni borrar avisos de pruebas.
- No enviar datos ficticios a AEAT producción. Solo entorno oficial de pruebas y acceso autorizado.
- No declarar validación externa, certificación o pruebas físicas que no se han ejecutado.
- Si falta un certificado, completar todo el trabajo independiente y dejar una prueba externa
  concreta con instrucciones. Nunca simular una respuesta AEAT correcta como aceptación real.

## Verificación
- Ejecutar `python -m pytest` después de cambios backend relevantes.
- Resolver dependencias, fijarlas y ejecutar `npm run typecheck` y `npm run build`.
- Añadir E2E de navegador y pruebas de accesibilidad. Probar Tauri real en Windows.
- `scripts/check_ts_syntax.cjs` es SOLO sintaxis: no puede declararse como typecheck o E2E.
- Revisar fallos y corregir código, no debilitar tests/validadores ni ocultar errores.
- Crear `reports/` con comandos, entorno, resultado y límites. No perseguir un número arbitrario de tests.
- Actualizar estado/checklist a medida que el trabajo se verifica; no dejar el documento de relevo obsoleto.

## Trabajo sostenido
Completa fases implementables sin pedir autorización para cada archivo. Las preguntas solo
bloquean cuando hay credenciales, consecuencias irreversibles o una decisión de negocio sin
alternativa segura. Conserva un registro breve de decisiones y progreso antes de compactar contexto.
No prometas trabajo en segundo plano ni des por terminado lo pendiente para cerrar la conversación.
