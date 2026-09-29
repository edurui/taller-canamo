# Asistencia local y automatizaciones

Estado verificado el 2026-09-23. Funciones opcionales, desactivadas inicialmente; el flujo
buscar → factura → imprimir no depende de ellas ni de Internet.

## Motores y revisión

- **Dictado**: Vosk 0.3.45 y modelo español pequeño 0.42. Micrófono mediante AudioWorklet,
  WAV PCM mono de 16 bits, entre 8 y 48 kHz; máximo dos minutos y 16 MB. Alternativamente
  se puede seleccionar un WAV. Parar o cerrar libera el micrófono; el audio no se guarda.
- **Documentación**: RapidOCR 3.9.2 con modelos locales de detección, orientación y
  reconocimiento latino, ejecutados por ONNX Runtime. PNG/JPEG/WebP/TIFF de una página,
  hasta 16 MB y 16 megapíxeles. Presenta original, texto, confianza y candidatos de matrícula,
  NIF, VIN, email o kilometraje. Las casillas para incorporar campos empiezan desmarcadas.
- **Redacción**: sin modelo configurado solo normaliza espacios e inicio de frase. Ollama
  es opcional en `127.0.0.1:11434`; requiere un modelo GGUF instalado localmente, cuya
  metadata se comprueba antes de enviar las notas. Rechaza proxies/modelos cloud y cambios
  de cifras. No se ha instalado ni evaluado aquí un LLM: no se atribuye calidad a esa ruta.

El usuario edita y aplica la propuesta y después guarda el documento/ficha. Ni el motor
ni el trabajo auxiliar escriben registros comerciales. Los trabajos usan start/status/cancel
y un único hilo auxiliar; el RPC y la búsqueda siguen disponibles durante el cálculo.
Cancelar descarta el resultado; el motor termina su cálculo local sin iniciar otro en paralelo.
Propuestas en memoria: caducidad de 15 minutos, máximo ocho resultados recientes, sin logs
con notas/imágenes/audio. Cerrar la aplicación descarta ese estado temporal.

Los modelos se preparan durante construcción con `scripts/prepare_assistant_models.py`;
URLs, versiones y SHA-256 están fijados en `scripts/assistant-models.lock.json`. El programa
verifica sus archivos antes de cargarlos y no descarga modelos al utilizar una factura.
Se incluyen sus avisos de licencia. No hay pagos por uso ni API comercial configurada.

## Funciones sin IA

Consulta determinista del historial del cliente o vehículo, conceptos frecuentes, conversión
de documentos, recordatorios, movimientos de stock, copias y mensajes preparados. La consulta
siempre identifica el cliente o vehículo; los resultados llevan documento, fecha y contexto.

Preparar un mensaje conserva la identidad documental y muestra el teléfono actual para
revisión. Copiarlo o abrir el enlace `https://wa.me/` requiere una acción del usuario. El
enlace externo transmite el texto al abrirlo; el programa no lo envía automáticamente.
Las pruebas no han abierto WhatsApp ni enviado mensajes reales.

## Evidencia y límites

- `tests/test_assistance.py` ejecuta los motores reales con una ficha y voz sintéticas y
  bloquea la red durante OCR/voz. El OCR recupera los tokens esperados. La voz contiene
  errores de reconocimiento: la revisión es necesaria.
- `reports/pytest-assistance-jobs-2026-09-23.xml`: 36 pruebas dirigidas (asistencia, jobs y
  relaciones documentales), incluidas búsqueda/emisión durante un proveedor lento inyectado,
  cancelación, idempotencia, expiración y ausencia de escrituras. El proveedor lento es una
  prueba controlada del protocolo, no una validación de calidad de Ollama.
- `e2e/assistance.spec.ts`: tres recorridos con navegador/backend reales: OCR+WAV,
  historial/mensaje sin envío y getUserMedia/AudioWorklet/Vosk. El micrófono es el dispositivo
  sintético del navegador; no se acredita un micrófono físico ni WebView2 Windows.
- Última ejecución conjunta dirigida: cinco E2E correctas en 10,8 s con copias por bloques,
  después de separar etiqueta y descripción accesible de los controles. Evidencia visual
  y fallos previos conservados en `reports/e2e-backup-streaming/`.

Las funciones de asistencia no determinan seguridad mecánica, diagnósticos ni obligaciones
fiscales. Nunca incorporan una reparación a una factura sin revisión y guardado explícitos.
