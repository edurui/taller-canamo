# Componentes de terceros y sus fuentes

Las bibliotecas se utilizan sin modificar. Se conservan los textos de licencia y los
avisos de copyright suministrados por cada distribución instalada. El inventario registra
versiones y separa los ecosistemas; también incluye herramientas de construcción que no
se ejecutan en el ordenador del usuario final.

- Python: distribuciones y hashes en `requirements*.lock`; fuentes en la ficha de cada
  versión de PyPI y en los enlaces `project_urls` del inventario.
- JavaScript: `package-lock.json`; cada paquete identifica licencia/versión en npm y su
  repositorio de origen. React y React DOM usan MIT.
- Rust/Tauri: `src-tauri/Cargo.lock`; fuentes y licencias del grafo Cargo registrado.
- Vosk 0.3.45, Apache-2.0: https://github.com/alphacep/vosk-api/tree/v0.3.45
  Modelo español: https://alphacephei.com/vosk/models ; pesos y hashes en el manifiesto.
- RapidOCR 3.9.2, Apache-2.0: https://github.com/RapidAI/RapidOCR/tree/v3.9.2
  Modelos de RapidAI/PaddleOCR y enlaces exactos en `assistant-models.lock.json`.
- SaxonC-HE 12.10.0, MPL-2.0: https://www.saxonica.com/html/saxon-c/index.html
  Código SaxonJ 12.10 utilizado por el motor:
  https://github.com/Saxonica/Saxon-HE/blob/main/12/source/saxon12-10source.zip
  Las fuentes de la envoltura C se publican en:
  https://github.com/Saxonica/Saxon-HE/tree/main/12/source
  Se incluyen los avisos del archivo binario oficial 12.10.0, cuyo hash queda registrado
  en `tools/legal/saxonche-source.json`. Solo se utiliza Home Edition sin clave comercial.
- Jackcess 5.0.1, Apache-2.0: https://github.com/jahlborn/jackcess
  Fuente de la versión: https://repo1.maven.org/maven2/io/github/jahlborn/jackcess/5.0.1/jackcess-5.0.1-sources.jar
- Temurin 17.0.20.1+1, GPLv2 con Classpath Exception y avisos por componente:
  https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.20.1%2B1
  Fuentes y proceso de compilación: https://github.com/adoptium/temurin-build
  y https://github.com/openjdk/jdk17u . El JRE conserva su carpeta `legal/` completa.
- OpenCV Python: https://github.com/opencv/opencv-python . El paquete aporta su aviso de
  terceros completo: FFmpeg bajo LGPL2.1 y, en Linux, Qt bajo LGPL3. Los algoritmos OCR
  usan procesamiento de imagen; no capturan vídeo con esas bibliotecas. Las fuentes y
  recetas de la versión están en ese repositorio y sus submódulos. Se conservan todos sus
  avisos, incluso los de módulos que no usa esta aplicación.
- ONNX Runtime: https://github.com/microsoft/onnxruntime ; MIT y ThirdPartyNotices.
- DejaVu Sans 2.37 (normal y negrita):
  https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37 .
  Fuentes TTF sin modificar, incorporadas a los PDF por subconjuntos. Licencias
  Bitstream Vera/Arev y cambios DejaVu en dominio público; texto oficial completo
  en `fonts/LICENSE.txt`, hashes y procedencia en `fonts/manifest.json`.
- Reglas EN16931: https://github.com/ConnectingEurope/eInvoicing-EN16931 . Se distribuyen
  sin modificar, junto con su fuente XSLT y licencia EUPL 1.2. Versiones y huellas en
  `backend/taller/schemas/b2b_ubl21/manifest.json`. Los XSD UBL conservan sus avisos OASIS.

El binario opcional de construcción `@napi-rs/lzma-linux-x64-gnu` 1.5.1 declara MIT
en el paquete oficial; el paquete y su repositorio de esa versión no aportan un archivo
LICENSE. El inventario lo identifica expresamente. Es una dependencia de Rollup para
construir la interfaz y no se distribuye como biblioteca ejecutable del instalador.

Para cambiar una biblioteca: instalar su distribución modificada en un entorno de
construcción separado, regenerar el inventario y reconstruir con `build_desktop.py`.
El código fuente y scripts de esta entrega permiten volver a enlazar/paquetizar las
bibliotecas. No se impone una prohibición de ingeniería inversa para depurar cambios
en bibliotecas amparados por sus licencias. No se requieren cuotas o claves comerciales
para los motores seleccionados. Conservar estas licencias y el acceso a las fuentes
correspondientes al redistribuir el instalador junto con el proyecto.
