# Etiqueta IA

Aplicación web local con una conversación guiada por una etiqueta, memoria editable en el navegador y generación opcional de voz e imágenes.

## Modo local sin clave de API

Necesita Python 3.10+, Ollama y conexión a Internet para descargar el modelo la primera vez. Después, las respuestas de texto pueden generarse localmente.

1. Instala Ollama para Windows desde [ollama.com/download/windows](https://ollama.com/download/windows) y deja Ollama abierto.
2. En PowerShell descarga e inicia un modelo local:

   ```powershell
   ollama run gemma3:4b
   ```

   La primera ejecución descarga el modelo (aprox. 3.4 GB). Para salir de su consola, escribe `/bye`; Ollama seguirá disponible en segundo plano.
3. Copia `.env.example` a `.env` si todavía no existe:

   ```powershell
   Copy-Item .env.example .env
   ```

4. Desde esta carpeta ejecuta `python app.py` y abre `http://127.0.0.1:8765`.

La configuración predeterminada usa Ollama local en `http://localhost:11434`, modelo `gemma3:4b`, voz del navegador y ComfyUI local para imágenes.

## Usar una clave de Ollama Cloud

La clave no se escribe en `OPENAI_API_KEY`. En el archivo `.env` usa estas variables:

```text
AI_PROVIDER=ollama
OLLAMA_API_KEY=tu_clave_de_ollama
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_TEXT_MODEL=gemma4:31b
```

Cloud envía las consultas a Ollama. Su acceso y límites dependen de la cuenta y del modelo; si quieres mantener las consultas en tu equipo, deja la URL local y no configures `OLLAMA_API_KEY`.

## Imágenes locales con ComfyUI

Para generar imágenes sin usar OpenAI, inicia ComfyUI en el puerto `8188` antes de activar «Imagen» en la app. En esta instalación, puedes abrir `%LOCALAPPDATA%\EtiquetaIA\ComfyUI\ComfyUI_windows_portable` en el Explorador y ejecutar `run_nvidia_gpu.bat`. Desde PowerShell, primero entra en esa carpeta y luego lanza el archivo:

```powershell
Set-Location "$env:LOCALAPPDATA\EtiquetaIA\ComfyUI\ComfyUI_windows_portable"
.\run_nvidia_gpu.bat
```

Deja abierta su ventana mientras generas. El checkpoint `v1-5-pruned-emaonly-fp16.safetensors` ya está en `ComfyUI/models/checkpoints` y coincide con el valor predeterminado de `COMFYUI_CHECKPOINT`. La app genera a 512 × 512 con 16 pasos. Al terminar, cierra la ventana de ComfyUI para liberar memoria y GPU; si luego quieres recuperar también el espacio del disco, elimina `%LOCALAPPDATA%\EtiquetaIA\ComfyUI`.

Voz utiliza la síntesis de voz del navegador y no necesita una API de audio. Las voces disponibles y su calidad dependen del sistema y del navegador.

## Variables opcionales

- `AI_PROVIDER=ollama` (predeterminado) o `AI_PROVIDER=openai`.
- `OLLAMA_BASE_URL`, `OLLAMA_TEXT_MODEL` y `OLLAMA_API_KEY` para Ollama local o Cloud.
- `COMFYUI_BASE_URL` y `COMFYUI_CHECKPOINT` para imágenes locales.
- `OPENAI_API_KEY`, `OPENAI_BASE_URL` y `OPENAI_TEXT_MODEL` si eliges `AI_PROVIDER=openai`.
- `HOST` y `PORT` para la dirección local de la app.

La memoria se guarda en `localStorage` del navegador; no reentrena modelos. Las claves se leen desde `.env` del servidor y no se envían al navegador. No subas `.env` a Git.
