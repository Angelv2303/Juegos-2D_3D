# Etiqueta IA — mejoras de octubre de 2026

## Cambios realizados

- Rediseño visual oscuro estilo *Generative Studio*, con acentos cian/violeta, paneles de contraste y estados más legibles.
- Se conserva la estructura y las funciones previas: etiqueta, descripción, memoria local, historial, voz, chat progresivo y descarga de medios.
- Gemma no se vuelve a cargar para preparar el prompt de una imagen: el prompt se compone localmente usando la etiqueta y la petición.
- Cuando el usuario solicita una imagen, la respuesta de texto libera Gemma (`keep_alive=0`) para dejar espacio a ComfyUI en la GPU de 4 GB.
- Una sola generación visual simultánea para reducir conflictos de VRAM.
- Pasos predeterminados de Stable Diffusion 1.5 reducidos de 25 a 16 para priorizar estabilidad y tiempo.
- Errores de workflow y de ejecución de ComfyUI muestran más detalles útiles.
- La imagen se genera en segundo plano desde la interfaz y se añade una opción para reintentar si falla.
- Valores predeterminados y documentación alineados con `gemma3:1b` y contexto 1024.

## Pruebas ejecutadas

- `python -m py_compile app.py`: correcto.
- `node --check app.js`: correcto.
- Prueba local HTTP: `/`, `/app.js`, `/styles.css` y `/api/status` responden correctamente.

## Limitación de las pruebas

En el entorno de desarrollo no estaba iniciado Ollama ni ComfyUI, por lo que no fue posible ejecutar una generación real de texto ni una imagen. Para probarlas en tu PC, inicia Ollama y ComfyUI y revisa cualquier detalle de error mostrado por Etiqueta IA y la consola de ComfyUI.
