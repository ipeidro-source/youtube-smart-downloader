# Limitaciones y notas de seguridad — v0.1

## Selección de idioma

- El metadato de idioma de yt-dlp/YouTube no es una verificación de la voz escuchada.
- `es-ES` exige metadato regional exacto; `es` acepta cualquier variante.
- Si hay varias pistas etiquetadas en el idioma elegido, se escoge la de mayor bitrate reportado.
- La opción «original» usa la nota `original` si existe y, si no, prefiere la pista del extractor. Este comportamiento no garantiza el idioma de origen.
- Sin pista de vídeo independiente o sin audio individual, se omite el vídeo para evitar mezclar idiomas.
- Si un vídeo desaparece, pasa a privado o YouTube limita la extracción, la aplicación informa del error y continúa.

## Distribución y dependencias

- La aplicación instala herramientas de terceros con `winget`, tras confirmación. No las descarga ni actualiza silenciosamente.
- `yt-dlp` y FFmpeg pueden cambiar sus requisitos y licencias. Revisarlos antes de nuevas releases.
- El `.exe` construido por CI **no está firmado** y puede activar SmartScreen.
- El botón de instalación requiere `winget`; si no está disponible, hay que instalar dependencias manualmente.
- No se incluyen las herramientas en el ejecutable para minimizar conflictos de licencia y facilitar sus actualizaciones.

## Privacidad y seguridad

- No tiene backend, cuentas, telemetría ni servicios propios.
- Las URLs se envían a los servicios consultados por yt-dlp y pueden quedar en el historial local de la aplicación o archivos de descarga.
- No se almacenan cookies, contraseñas ni claves API.
- Se admiten solamente URLs HTTP(S) con dominios YouTube conocidos; esto no es un sandbox ni una garantía contra contenido malicioso.
- Revisa el copyright y las condiciones del servicio antes de descargar contenido.

## Mejoras posteriores

- Pruebas de integración con fixtures del extractor y mocks de subprocess (sin realizar descargas reales en CI).
- Detección más exhaustiva de audio original y diagnóstico detallado previo a descargas.
- Actualizador opcional para herramientas externas y firma de código.
- Mejor tratamiento de listas modificadas y detección de elementos ya presentes.
- Internacionalización de la interfaz.
