# YouTube Smart Downloader

Aplicación gratuita y de código abierto para Windows, con interfaz gráfica en castellano, que usa **yt-dlp** para descargar vídeos y listas de reproducción de YouTube y permite elegir el **idioma del audio**.

> Solo descarga contenido cuando tengas derecho o autorización para hacerlo. Respeta los derechos de autor y las condiciones de los servicios.

## Funcionalidades (v0.1.0)

- Un vídeo o una lista completa; orden numerado y subcarpeta opcional por lista.
- Carpeta de destino elegible y preferencias recordadas entre ejecuciones.
- Audio: español (cualquier variante), español de España (`es-ES`), español de Latinoamérica (`es-419`), inglés, original o automático.
- **Modo estricto**: si la pista elegida no está identificada por idioma, omite el vídeo. Alternativamente permite usar el audio original/predeterminado (marcado como no verificado).
- Selector de resolución máxima: mejor, 1080p, 720p, 480p.
- MP4 final gracias a FFmpeg; progreso, cancelación, reanudación y archivo anti-duplicados.
- Informe JSON de vídeos procesados, omitidos y fallos.
- Botón de instalación de yt-dlp + FFmpeg + Deno mediante `winget` (Windows).
- Tests, linting, CI multiplataforma y compilación Windows por GitHub Actions.

## Instalación para usuarios de Windows

1. Descarga `YouTubeSmartDownloader.exe` desde **Releases** (una vez publicada la primera versión). Alternativamente, compílalo desde el código.
2. Ejecuta el programa. Windows SmartScreen puede advertir porque el ejecutable no está firmado; verifica siempre su procedencia.
3. Si faltan dependencias, pulsa **Instalar herramientas**. Necesitas Windows con `winget` y conexión a Internet. Acepta el cuadro de confirmación de la aplicación.
4. **Cierra y vuelve a abrir** el programa después de instalar para que Windows actualice la ruta de las herramientas.
5. Pega el enlace, elige Vídeo o Lista, carpeta, idioma, política de ausencia y calidad; pulsa **Descargar**.

La versión `exe` no requiere instalar Python, pero **yt-dlp, FFmpeg y Deno son herramientas externas**, instaladas mediante winget. No se distribuyen dentro del ejecutable.

## Desarrollo

Requiere Python 3.11+:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m youtube_smart_downloader
pytest -q
ruff check .
```

Build Windows:

```powershell
pyinstaller --noconfirm --clean --onefile --windowed --name YouTubeSmartDownloader --paths src src/youtube_smart_downloader/__main__.py
```

CI: `.github/workflows/ci.yml` ejecuta las pruebas y crea un artefacto Windows. La publicación de un tag `v*` activa `.github/workflows/release.yml` y crea un GitHub Release con el `.exe`.

## Idiomas: límites reales

YouTube puede publicar varias pistas de audio con metadatos de idioma, pero no siempre los proporciona o pueden ser incorrectos. Por diseño, en modo estricto el programa no inventa el idioma: omite los vídeos sin pista etiquetada. El selector `es-ES` exige la etiqueta regional; una etiqueta `es` genérica **no prueba** que sea castellano peninsular. La opción original intenta detectar la pista original; cuando no hay prueba explícita, utiliza las preferencias del extractor y lo indica como **no verificado**.

Un vídeo con audio incrustado únicamente en un formato combinado puede omitirse para evitar cambiar silenciosamente la pista. La disponibilidad de audios multilingües depende de cada vídeo. Se recomienda revisar el informe y escuchar una muestra antes de descargar listas largas.

## Comportamiento de las descargas

- Se utiliza la opción `--download-archive` de yt-dlp por carpeta, para evitar re-descargas de vídeos terminados.
- Al cancelar, yt-dlp conserva los archivos parciales habitualmente; vuelve a usar la misma carpeta para reanudar.
- La conversión a MP4 puede consumir CPU, ocupar espacio temporal y tardar dependiendo de los códecs de origen.
- Una descarga que ya figure en el archivo de historial puede mostrarse como procesada, aunque yt-dlp la omita: revisa el log y el archivo del historial para distinguir ambos casos.

## Arquitectura

- `core.py`: política de idioma, resolución, construcción de argumentos (funciones puras).
- `engine.py`: lectura de metadatos, descargas, cancelación, informes y gestión de dependencias.
- `app.py`: interfaz CustomTkinter y mensajería asíncrona mediante cola para mantener la UI reactiva.
- `settings.py`: preferencias locales en `%APPDATA%/YouTubeSmartDownloader/settings.json`.
- `tests/`: pruebas unitarias sin acceso a YouTube.

Consulta [LIMITATIONS.md](docs/LIMITATIONS.md) para riesgos conocidos, decisiones de privacidad y el alcance de la primera versión.

## Licencias y atribuciones

El código propio de este repositorio está bajo [MIT](LICENSE).

Este proyecto **no está afiliado a YouTube ni a Google**. Se apoya en herramientas independientes instaladas por el usuario: [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense para el código fuente; los ejecutables distribuidos por upstream pueden tener condiciones GPL adicionales) y [FFmpeg](https://ffmpeg.org/legal.html) (LGPL o GPL, dependiendo de la compilación). También puede requerir [Deno](https://deno.com/), con su licencia aplicable. El ejecutable creado aquí no empaqueta esas herramientas. CustomTkinter y las dependencias Python conservan sus propias licencias.

## Contribuir

Abre una issue con descripción y pasos para reproducir. Envía una PR con tests cuando cambie la lógica de selección o descarga. No incluyas cookies de sesión, tokens, ni vídeos descargados en el repositorio.

## Publicar el proyecto en el repositorio del propietario

Como alternativa a subir los archivos manualmente, el ZIP incluye `PUBLICAR_EN_GITHUB.ps1`. Requiere `git`, GitHub CLI (`gh`) y sesión iniciada con `gh auth login` con permisos de escritura sobre `ipeidro-source/youtube-smart-downloader`. Desde PowerShell, en la carpeta descomprimida:

```powershell
.\PUBLICAR_EN_GITHUB.ps1
```

Clona el repositorio en una carpeta temporal, prepara `feature/desktop-app-v0.1`, realiza commit y push, y abre una PR contra `main`. **No hace merge ni crea release automáticamente**. Si esa rama ya existe, debes cambiar su nombre en el script.
