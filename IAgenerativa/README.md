# Etiqueta IA

Aplicación web local con conversación guiada por una etiqueta, memoria editable, historial persistente en el navegador y generación opcional de voz e imágenes. El backend usa solo la biblioteca estándar de Python; Piper y ComfyUI son procesos externos opcionales.

## Inicio local

1. Instala Python 3.10 o posterior y [Ollama para Windows](https://ollama.com/download/windows).
2. Descarga el modelo de texto ligero y déjalo disponible en Ollama:

   ```powershell
   ollama run gemma3:1b
   ```

   La primera ejecución descarga el modelo. `/bye` cierra la consola interactiva; Ollama queda disponible como servicio local.
3. Copia `.env.example` como `.env` si aún no existe:

   ```powershell
   Copy-Item .env.example .env
   ```

4. Desde esta carpeta ejecuta `python app.py` y abre `http://127.0.0.1:8765`.

El servidor local solo entrega `/`, `/index.html`, `/app.js` y `/styles.css`, además de medios generados dentro de `outputs/`. No publica otros archivos del proyecto. La conversación se transmite por fragmentos; si Ollama no permite streaming, el backend responde con el modo JSON habitual.

## Imágenes con ComfyUI y Stable Diffusion 1.5

Activa «Imagen» para crear una imagen según la etiqueta, la pregunta y la respuesta. La aplicación convierte esa información en un prompt corto en inglés con Ollama y lo registra en la consola del servidor. Si Ollama no puede redactarlo, se usa un prompt de respaldo.

El workflow predeterminado usa SD 1.5 a 512 × 512, 16 pasos, `dpmpp_2m`, scheduler `karras` y CFG 6.5. Estos valores priorizan una generación más manejable en 4 GB de VRAM; puedes aumentar `COMFYUI_STEPS` si tu equipo lo soporta. Para una imagen vertical, cambia en `.env`:

```text
COMFYUI_WIDTH=512
COMFYUI_HEIGHT=768
```

### Instalar un checkpoint SD 1.5 mejor

1. Descarga desde la página oficial del modelo un checkpoint **SD 1.5** en `.safetensors` y formato fp16. DreamShaper 8 y Realistic Vision son opciones para probar; revisa la licencia de cada descarga.
2. Copia el archivo a `ComfyUI/models/checkpoints/`.
3. Pon el nombre del archivo, incluido `.safetensors`, en `COMFYUI_CHECKPOINT` dentro de `.env`.
4. Reinicia ComfyUI para que detecte el checkpoint.

Si ComfyUI informa falta de memoria CUDA o el equipo se queda sin VRAM, lánzalo con `--lowvram`. Para diagnosticar errores, revisa ahora el mensaje detallado mostrado por la interfaz y la consola de ComfyUI. En la instalación portable de Windows, edita `run_nvidia_gpu.bat` y añade el argumento a la línea que ejecuta `ComfyUI\main.py`, por ejemplo:

```bat
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --lowvram
```

La ruta exacta depende de dónde extrajiste ComfyUI; conserva los argumentos que ya tenga el archivo y solo agrega `--lowvram`. Para volver al modo automático, quítalo.

La app serializa el uso local de Ollama y ComfyUI para evitar competir por los 4 GB de VRAM. Si se solicita una imagen, Ollama libera Gemma al terminar la respuesta; la descripción visual se prepara localmente sin cargar de nuevo el modelo de texto. ComfyUI libera los modelos al terminar el trabajo. Por eso, mientras una imagen se procesa, una nueva petición de texto puede quedar esperando el turno de GPU. Las imágenes se ejecutan de una en una y la interfaz permite reintentar si se produce un error.

### LoRA LCM opcional

Para acelerar SD 1.5, instala un LoRA LCM compatible con SD 1.5 en `ComfyUI/models/loras/` y asigna su nombre en `.env`:

```text
COMFYUI_LCM_LORA=lcm-lora-sd15.safetensors
```

Con LCM la aplicación selecciona sampler `lcm`, 8 pasos, CFG 1.5 y scheduler `normal`. Borra o comenta la variable para volver al workflow de 25 pasos.

## Voz

`TTS_PROVIDER=browser` es el valor predeterminado. Usa `speechSynthesis` del navegador, prioriza una voz `es-CO` y limpia markdown y emojis. Divide respuestas largas en frases para reducir los cortes de Chrome. El navegador no crea archivos de audio descargables; la app guarda la preferencia de volver a narrar en el historial.

### Piper local en CPU (opcional)

1. En PowerShell instala Piper en el entorno de Python que usarás para la app:

   ```powershell
   python -m pip install piper-tts
   python -m piper.download_voices
   ```

2. Elige un identificador español (`es_MX`, `es_ES` o `es_AR`) de la lista de voces y descárgalo. Sustituye `<ID_DE_VOZ>` por el nombre exacto que muestre la lista:

   ```powershell
   python -m piper.download_voices <ID_DE_VOZ> --data-dir "$env:LOCALAPPDATA\EtiquetaIA\voices"
   ```

   Conserva juntos el archivo `.onnx` y su archivo de configuración `.onnx.json`. Revisa la licencia indicada para la voz elegida.
3. Usa el ejecutable `piper.exe` instalado por el paquete y el `.onnx` de la voz en `.env`:

   ```text
   TTS_PROVIDER=piper
   PIPER_PATH=C:\Users\tu_usuario\AppData\Local\Programs\Python\Python312\Scripts\piper.exe
   PIPER_VOICE=C:\Users\tu_usuario\AppData\Local\EtiquetaIA\voices\<archivo-de-voz>.onnx
   ```

   Ajusta las rutas a tu instalación. Piper se ejecuta sin la opción `--cuda`, por lo que la síntesis se hace en CPU. La app guarda el WAV en `outputs/`, lo agrega al historial y muestra controles de reproducción y descarga.

También se conserva `TTS_PROVIDER=openai` como opción anterior; requiere `OPENAI_API_KEY` en `.env`. No pongas claves en el código ni en `.env.example`.

## Variables principales

- `AI_PROVIDER=ollama` (predeterminado) o `openai`.
- `OLLAMA_BASE_URL`, `OLLAMA_TEXT_MODEL`, `OLLAMA_NUM_CTX=1024`, `OLLAMA_TEMPERATURE=0.65` y `OLLAMA_KEEP_ALIVE=5m`.
- `COMFYUI_BASE_URL`, `COMFYUI_CHECKPOINT`, `COMFYUI_WIDTH`, `COMFYUI_HEIGHT`, `COMFYUI_STEPS`, `COMFYUI_SAMPLER`, `COMFYUI_SCHEDULER`, `COMFYUI_CFG` y `COMFYUI_LCM_LORA`.
- `TTS_PROVIDER=browser|piper|openai`, `PIPER_PATH` y `PIPER_VOICE`.
- `OPENAI_API_KEY`, `OPENAI_BASE_URL` y `OPENAI_TEXT_MODEL` solo si eliges OpenAI.
- `HOST` y `PORT` para el servidor web.

La memoria y el historial se guardan en `localStorage`. Las imágenes y los WAV/MP3 quedan en `IAgenerativa/outputs/`; el historial conserva sus rutas para mostrarlos después de recargar. Elimina esa carpeta si quieres borrar los medios guardados.

## Lista de comprobación manual

1. **Archivos estáticos:** inicia `python app.py`; abre `http://127.0.0.1:8765/` y confirma que carga. En PowerShell ejecuta `curl.exe -i http://127.0.0.1:8765/.env` y `curl.exe -i http://127.0.0.1:8765/app.py`; ambos deben responder `404`. `curl.exe -i "http://127.0.0.1:8765/app.js?cache=1"` debe responder `200`.
2. **Prompt y workflow de imagen:** activa «Imagen», pregunta algo visual y confirma en la consola que el prompt es breve, en inglés y sin texto incrustado. Revisa que aparezca el estado de cola/generación y que al terminar muestre la imagen y «Descargar imagen». Cambia temporalmente ancho/alto o el checkpoint en `.env` para verificar la configuración.
3. **LCM:** instala un LoRA LCM compatible y configura `COMFYUI_LCM_LORA`. Genera una imagen y confirma que ComfyUI acepta sampler `lcm` con 6–8 pasos y CFG 1–2. Luego comenta esa variable y comprueba que vuelve a 25 pasos.
4. **Voz del navegador:** deja `TTS_PROVIDER=browser`, activa «Voz» y reproduce una respuesta con markdown, emojis y varios párrafos; debe pronunciar el texto limpio por partes. Recarga la página y prueba «Escuchar» desde una respuesta narrada previamente.
5. **Piper:** instala una voz española, configura `TTS_PROVIDER=piper`, `PIPER_PATH` y `PIPER_VOICE`, reinicia el servidor y reproduce una respuesta. Comprueba que el reproductor suena, que se puede descargar el WAV y que el audio sigue en el historial al recargar.
6. **Streaming, memoria e historial:** envía una respuesta larga y confirma que la burbuja va creciendo antes de terminar. Envía una pregunta de seguimiento y comprueba que recuerda mensajes anteriores y notas de memoria sin duplicar turnos.
7. **Persistencia y trabajos:** genera una imagen y audio, recarga y confirma que se muestran. Mientras ComfyUI procesa una imagen, comprueba que la solicitud de imagen devuelve enseguida un `job_id`, que el estado cambia al consultar `/api/image/<job_id>` y que la página continúa respondiendo.

## Ollama Cloud y OpenAI (opcionales)

Para Ollama Cloud define `OLLAMA_API_KEY`, `OLLAMA_BASE_URL=https://ollama.com` y un modelo disponible en tu cuenta. Con una RTX 2050 de 4 GB, el modo recomendado para generación local es `gemma3:1b`; las solicitudes locales de chat se bloquean durante trabajos de ComfyUI.

Para OpenAI usa `AI_PROVIDER=openai` y coloca `OPENAI_API_KEY` solo en `.env`. Las claves no se envían al navegador.
