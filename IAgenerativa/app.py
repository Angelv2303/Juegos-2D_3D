"""Servidor local para Etiqueta IA, una experiencia multimodal acotada por contexto."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = ROOT / "outputs"
STATIC_ROUTES = {
    "/": ROOT / "index.html",
    "/index.html": ROOT / "index.html",
    "/app.js": ROOT / "app.js",
    "/styles.css": ROOT / "styles.css",
}
MEDIA_ROUTE = re.compile(r"^/outputs/([a-f0-9]{32})\.(png|wav|mp3)$")


def load_local_env():
    """Carga variables simples de .env sin reemplazar valores del proceso."""
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if value[:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        if name and name not in os.environ:
            os.environ[name] = value


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


load_local_env()
OLLAMA_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "https://ollama.com" if OLLAMA_KEY else "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "gemma4:31b" if OLLAMA_KEY else "gemma3:1b")
OLLAMA_NUM_CTX = max(512, min(8192, env_int("OLLAMA_NUM_CTX", 1024)))
OLLAMA_TEMPERATURE = max(0.0, min(2.0, env_float("OLLAMA_TEMPERATURE", 0.65)))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "5m").strip() or "5m"
COMFY_BASE = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188").rstrip("/")
COMFY_CHECKPOINT = os.getenv("COMFYUI_CHECKPOINT", "v1-5-pruned-emaonly-fp16.safetensors")
COMFYUI_WIDTH = env_int("COMFYUI_WIDTH", 512)
COMFYUI_HEIGHT = env_int("COMFYUI_HEIGHT", 512)
COMFYUI_STEPS = env_int("COMFYUI_STEPS", 16)
COMFYUI_SAMPLER = os.getenv("COMFYUI_SAMPLER", "dpmpp_2m").strip() or "dpmpp_2m"
COMFYUI_SCHEDULER = os.getenv("COMFYUI_SCHEDULER", "karras").strip() or "karras"
COMFYUI_CFG = env_float("COMFYUI_CFG", 6.5)
COMFYUI_LCM_LORA = os.getenv("COMFYUI_LCM_LORA", "").strip()
COMFY_DEFAULT_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "EtiquetaIA" / "ComfyUI" / "ComfyUI_windows_portable"
COMFY_INSTALL_DIR = Path(os.getenv("COMFYUI_INSTALL_DIR", str(COMFY_DEFAULT_DIR))).expanduser()
COMFY_AUTO_START = os.getenv("COMFYUI_AUTO_START", "true").strip().lower() not in {"0", "false", "no", "off"}
COMFY_START_LOCK = threading.Lock()
OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
SPEECH_MODEL = os.getenv("OPENAI_SPEECH_MODEL", "gpt-4o-mini-tts")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "browser").strip().lower()
if TTS_PROVIDER not in {"browser", "piper", "openai"}:
    TTS_PROVIDER = "browser"
PIPER_PATH = os.getenv("PIPER_PATH", "").strip()
PIPER_VOICE = os.getenv("PIPER_VOICE", "").strip()
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()
MAX_BODY = 1_000_000
MODEL_RESOURCE_LOCK = threading.Lock()
IMAGE_JOBS: dict[str, dict] = {}
IMAGE_JOBS_LOCK = threading.Lock()


class APIError(Exception):
    pass


def request_json(base: str, path: str, payload: dict | None = None, *, key: str = "", timeout: int = 120):
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = None
    method = "GET"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = Request(f"{base}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:900]
        try:
            parsed = json.loads(details)
            details = parsed.get("error", {}).get("message", details) if isinstance(parsed.get("error"), dict) else parsed.get("error", details)
        except (ValueError, AttributeError):
            pass
        raise APIError(f"Servicio {base} respondió {exc.code}: {details}") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise APIError(f"No se pudo conectar con {base}: {exc}") from exc


def request_bytes(base: str, path: str, *, key: str = "", timeout: int = 120) -> bytes:
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = Request(f"{base}{path}", headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, TimeoutError, URLError, OSError) as exc:
        raise APIError(f"No se pudo descargar el resultado desde {base}: {exc}") from exc


def ollama_messages(instructions: str, prompt: str, history: list) -> list[dict]:
    messages = [{"role": "system", "content": instructions}]
    for item in history[-8:]:
        if not isinstance(item, dict):
            continue
        role = "assistant" if item.get("role") == "assistant" else "user"
        content = str(item.get("content", ""))[:900]
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})
    return messages


def ollama_payload(instructions: str, prompt: str, history: list, *, stream: bool,
                   release_after: bool = False) -> dict:
    return {
        "model": OLLAMA_MODEL,
        "messages": ollama_messages(instructions, prompt, history),
        "stream": stream,
        "options": {"temperature": OLLAMA_TEMPERATURE, "num_ctx": OLLAMA_NUM_CTX},
        "keep_alive": 0 if release_after else OLLAMA_KEEP_ALIVE,
    }


def make_ollama_reply(instructions: str, prompt: str, history: list, *, release_after: bool = False) -> str:
    result = request_json(
        OLLAMA_BASE, "/api/chat",
        ollama_payload(instructions, prompt, history, stream=False, release_after=release_after),
        key=OLLAMA_KEY, timeout=240,
    )
    return str(result.get("message", {}).get("content", "")).strip()


def iter_ollama_reply(instructions: str, prompt: str, history: list, *, release_after: bool = False):
    request = Request(
        f"{OLLAMA_BASE}/api/chat",
        data=json.dumps(ollama_payload(instructions, prompt, history, stream=True,
                                       release_after=release_after)).encode("utf-8"),
        headers={"Accept": "application/x-ndjson", "Content-Type": "application/json",
                 **({"Authorization": f"Bearer {OLLAMA_KEY}"} if OLLAMA_KEY else {})},
        method="POST",
    )
    try:
        with urlopen(request, timeout=240) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                try:
                    part = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise APIError("Ollama devolvió un fragmento de transmisión no válido.") from exc
                text = str(part.get("message", {}).get("content", ""))
                if text:
                    yield text
                if part.get("done"):
                    return
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:900]
        raise APIError(f"Ollama respondió {exc.code}: {details}") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise APIError(f"No se pudo conectar con {OLLAMA_BASE}: {exc}") from exc


def make_openai_reply(instructions: str, prompt: str, history: list) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise APIError("Falta OPENAI_API_KEY. Cambia AI_PROVIDER=ollama para usar el modo local.")
    result = request_json(OPENAI_BASE, "/responses", {
        "model": OPENAI_TEXT_MODEL,
        "instructions": instructions,
        "input": [
            *[{"role": "assistant" if item.get("role") == "assistant" else "user",
               "content": str(item.get("content", ""))[:900]}
              for item in history[-8:] if isinstance(item, dict) and item.get("content")],
            {"role": "user", "content": prompt},
        ],
        "max_output_tokens": 1200,
    }, key=key)
    return str(result.get("output_text", "")).strip()


def ensure_comfyui() -> None:
    """Arranca ComfyUI bajo demanda si el servicio local está apagado."""
    try:
        request_json(COMFY_BASE, "/system_stats", timeout=3)
        return
    except APIError as first_error:
        if not COMFY_AUTO_START or os.name != "nt":
            raise first_error
        if urllib.parse.urlsplit(COMFY_BASE).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise first_error

    with COMFY_START_LOCK:
        try:
            request_json(COMFY_BASE, "/system_stats", timeout=3)
            return
        except APIError:
            pass

        launcher = COMFY_INSTALL_DIR / "run_nvidia_gpu.bat"
        if not launcher.is_file():
            raise APIError(
                f"ComfyUI no está activo y no encontré el lanzador en {launcher}. "
                "Revisa COMFYUI_INSTALL_DIR en .env."
            )
        try:
            subprocess.Popen(
                ["cmd.exe", "/c", str(launcher)],
                cwd=str(COMFY_INSTALL_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except OSError as exc:
            raise APIError(f"No pude iniciar ComfyUI: {exc}") from exc

        deadline = time.monotonic() + 180
        last_error = ""
        while time.monotonic() < deadline:
            try:
                request_json(COMFY_BASE, "/system_stats", timeout=3)
                return
            except APIError as exc:
                last_error = str(exc)
                time.sleep(2)
        raise APIError(
            "ComfyUI no terminó de iniciar. Revisa la ventana de ComfyUI para ver el motivo. "
            f"{last_error}"
        )


def clean_image_prompt(text: str) -> str:
    text = re.sub(r"[\r\n\"'`]+", " ", str(text))
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-")
    return " ".join(text.split()[:60])


def fallback_image_prompt(label: str, question: str) -> str:
    topic = re.sub(r"[^\w\s,-]", " ", f"{label} {question}", flags=re.UNICODE)
    topic = " ".join(topic.split()[:18])
    return clean_image_prompt(
        f"Editorial digital illustration inspired by {topic or 'the conversation topic'}, "
        "a clear central subject in a fitting setting, cinematic soft lighting, "
        "refined colors, polished concept art, balanced composition, no text"
    )


def build_image_prompt(label: str, question: str, answer: str) -> str:
    """Construye un prompt sin volver a cargar Gemma: útil en GPU con poca VRAM."""
    # No invocamos Ollama aquí. Cuando el usuario solicita imagen, el chat ya
    # puede liberar Gemma y esta descripción directa evita una segunda carga del modelo.
    source = question or answer or label
    source = re.sub(r"https?://\S+|[<>`{}]", " ", str(source))
    source = " ".join(source.split())[:320]
    topic = " ".join((label + " " + source).split())[:42]
    return clean_image_prompt(
        f"High quality digital illustration of {topic or 'a creative concept'}, "
        "clear central subject, coherent environment, cinematic soft lighting, "
        "rich but balanced colors, polished concept art, detailed composition, no text, no watermark"
    )


def save_output(data: bytes, extension: str) -> str:
    output_root = ensure_outputs_dir()
    file_id = uuid.uuid4().hex
    (output_root / f"{file_id}.{extension}").write_bytes(data)
    return f"/outputs/{file_id}.{extension}"


def ensure_outputs_dir() -> Path:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    output_root = OUTPUTS_DIR.resolve()
    if output_root.parent != ROOT.resolve():
        raise APIError("La carpeta de medios debe permanecer dentro del proyecto.")
    return output_root


def update_image_job(job_id: str, **changes) -> None:
    with IMAGE_JOBS_LOCK:
        if job_id in IMAGE_JOBS:
            IMAGE_JOBS[job_id].update(changes)


def _queue_position(prompt_id: str) -> str:
    queue = request_json(COMFY_BASE, "/queue", timeout=10)
    for item in queue.get("queue_running", []):
        if len(item) > 1 and item[1] == prompt_id:
            return "running"
    for item in queue.get("queue_pending", []):
        if len(item) > 1 and item[1] == prompt_id:
            return "queued"
    return "unknown"


def make_local_image(prompt: str, job_id: str) -> str:
    ensure_comfyui()
    print(f"[Imagen ComfyUI] {prompt}")
    use_lcm = bool(COMFYUI_LCM_LORA)
    width = max(256, min(768, COMFYUI_WIDTH))
    height = max(256, min(768, COMFYUI_HEIGHT))
    width = (width // 64) * 64
    height = (height // 64) * 64
    if width * height > 512 * 768:
        width, height = 512, 768
    steps = max(6, min(8, COMFYUI_STEPS)) if use_lcm else max(10, min(40, COMFYUI_STEPS))
    cfg = max(1.0, min(2.0, COMFYUI_CFG)) if use_lcm else max(1.0, min(12.0, COMFYUI_CFG))
    sampler = "lcm" if use_lcm else COMFYUI_SAMPLER
    scheduler = "normal" if use_lcm else COMFYUI_SCHEDULER
    model_ref, clip_ref = ["1", 0], ["1", 1]
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": COMFY_CHECKPOINT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": clip_ref}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "text, letters, watermark, blurry, lowres, deformed, extra fingers, bad anatomy", "clip": clip_ref}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": secrets.randbelow(2**32), "steps": steps, "cfg": cfg, "sampler_name": sampler, "scheduler": scheduler, "denoise": 1, "model": model_ref, "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "Etiqueta", "images": ["6", 0]}},
    }
    if use_lcm:
        workflow["8"] = {"class_type": "LoraLoader", "inputs": {
            "lora_name": COMFYUI_LCM_LORA, "strength_model": 1.0, "strength_clip": 1.0,
            "model": model_ref, "clip": clip_ref,
        }}
        workflow["5"]["inputs"]["model"] = ["8", 0]
        workflow["2"]["inputs"]["clip"] = ["8", 1]
        workflow["3"]["inputs"]["clip"] = ["8", 1]
    queued = request_json(COMFY_BASE, "/prompt", {"prompt": workflow, "client_id": "etiqueta-ia"}, timeout=20)
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        node_errors = queued.get("node_errors", {})
        details = []
        if isinstance(node_errors, dict):
            for node_id, info in node_errors.items():
                if not isinstance(info, dict):
                    continue
                for item in info.get("errors", []):
                    if isinstance(item, dict):
                        message = item.get("message") or item.get("details")
                        if message:
                            details.append(f"Nodo {node_id}: {message}")
        detail = " ".join(details)[:700]
        raise APIError("ComfyUI rechazó el workflow" + (f": {detail}" if detail else ". Comprueba el nombre del checkpoint y los nodos instalados."))
    update_image_job(job_id, status="queued", message="En cola de ComfyUI", prompt_id=prompt_id)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            position = _queue_position(prompt_id)
            if position == "running":
                update_image_job(job_id, status="running", message="ComfyUI está generando la imagen")
            elif position == "queued":
                update_image_job(job_id, status="queued", message="Esperando turno en ComfyUI")
        except APIError:
            pass
        history = request_json(COMFY_BASE, f"/history/{urllib.parse.quote(prompt_id)}", timeout=20)
        record = history.get(prompt_id, {})
        images = [image for node in record.get("outputs", {}).values() for image in node.get("images", [])]
        if images:
            image = images[0]
            query = urllib.parse.urlencode({"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")})
            output_url = save_output(request_bytes(COMFY_BASE, f"/view?{query}", timeout=60), "png")
            return output_url
        status = record.get("status", {})
        if status.get("status_str") == "error":
            messages = status.get("messages", [])
            details = []
            for entry in messages:
                if isinstance(entry, (list, tuple)) and len(entry) > 1 and entry[0] == "execution_error":
                    info = entry[1] if isinstance(entry[1], dict) else {}
                    message = info.get("exception_message")
                    if message:
                        details.append(str(message))
            detail = " ".join(dict.fromkeys(details))[:700]
            raise APIError("ComfyUI reportó un error de ejecución" + (f": {detail}" if detail else ". Revisa el checkpoint, los nodos y la memoria VRAM."))
    raise APIError("ComfyUI tardó demasiado. Comprueba que el modelo local esté cargado.")


def image_job_worker(job_id: str, label: str, question: str, answer: str) -> None:
    try:
        update_image_job(job_id, status="preparing", message="Preparando el prompt visual")
        # En equipos con 4 GB de VRAM se ejecuta un trabajo visual a la vez.
        # El prompt se construye localmente y no vuelve a cargar Gemma.
        with MODEL_RESOURCE_LOCK:
            prompt = build_image_prompt(label, question, answer)
            update_image_job(job_id, prompt=prompt, status="starting", message="Prompt listo; preparando memoria gráfica")
            # Gemma se descarga tras una respuesta que solicita imagen (keep_alive=0).
            # Esta llamada a ComfyUI libera cualquier modelo que aún ocupe VRAM.
            try:
                request_json(COMFY_BASE, "/free", {"unload_models": True, "free_memory": True}, timeout=20)
            except APIError as exc:
                print(f"[VRAM] ComfyUI no confirmó la liberación inicial: {exc}")
            image_url = make_local_image(prompt, job_id)
            try:
                request_json(COMFY_BASE, "/free", {"unload_models": True, "free_memory": True}, timeout=20)
            except APIError as exc:
                print(f"[VRAM] ComfyUI no confirmó la liberación final: {exc}")
        update_image_job(job_id, status="completed", message="Imagen lista", image=image_url)
    except Exception as exc:
        update_image_job(job_id, status="error", message="No se pudo crear la imagen", error=str(exc))


def start_image_job(label: str, question: str, answer: str) -> str:
    job_id = uuid.uuid4().hex
    with IMAGE_JOBS_LOCK:
        activos = sum(job["status"] not in {"completed", "error"} for job in IMAGE_JOBS.values())
        if activos >= 1:
            raise APIError("Ya hay una imagen en proceso. En una GPU de 4 GB se permite una sola generación a la vez.")
        IMAGE_JOBS[job_id] = {
            "job_id": job_id, "status": "queued", "message": "Trabajo recibido",
            "image": None, "error": None, "prompt": None, "created_at": time.time(),
        }
    worker = threading.Thread(target=image_job_worker,
                              args=(job_id, label, question, answer), daemon=True)
    worker.start()
    return job_id


def local_status(base: str, path: str, key: str = "") -> tuple[bool, str]:
    try:
        request_json(base, path, key=key, timeout=3)
        return True, "Conectado"
    except APIError as exc:
        return False, str(exc)


def call_api(path: str, payload: dict, *, binary: bool = False):
    """Llama a OpenAI solo para las funciones que el usuario habilitó explícitamente."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise APIError("Esta función de OpenAI no está configurada. Usa el modo local o activa la voz del navegador.")
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{OPENAI_BASE}{path}",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            data = response.read()
        return data if binary else json.loads(data.decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:900]
        try:
            details = json.loads(details).get("error", {}).get("message", details)
        except (ValueError, AttributeError):
            pass
        raise APIError(f"La API respondió {exc.code}: {details}") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise APIError(f"No se pudo conectar con la API: {exc}") from exc


def clean_speech_text(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"!?(\[([^\]]*)\])\([^)]*\)", r"\2", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[`*_>#~|]", " ", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:4000]


def generate_speech(text: str) -> dict:
    provider = TTS_PROVIDER if TTS_PROVIDER in {"browser", "piper", "openai"} else "browser"
    if provider == "browser":
        return {"provider": "browser", "model": "speechSynthesis"}
    if provider == "piper":
        if not PIPER_PATH or not PIPER_VOICE:
            raise APIError("Configura PIPER_PATH y PIPER_VOICE en .env para activar Piper.")
        executable = Path(PIPER_PATH).expanduser()
        voice_model = Path(PIPER_VOICE).expanduser()
        if not executable.is_file():
            raise APIError(f"No encuentro el ejecutable de Piper: {executable}")
        if not voice_model.is_file():
            raise APIError(f"No encuentro el modelo de voz de Piper: {voice_model}")
        output_path = ensure_outputs_dir() / f"{uuid.uuid4().hex}.wav"
        try:
            result = subprocess.run(
                [str(executable), "--model", str(voice_model), "--output_file", str(output_path)],
                input=text, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise APIError(f"No se pudo ejecutar Piper: {exc}") from exc
        if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size <= 44:
            output_path.unlink(missing_ok=True)
            details = result.stderr.strip()[-500:] or "Piper no produjo un WAV válido."
            raise APIError(details)
        audio = output_path.read_bytes()
        return {
            "provider": "piper", "model": "Piper local (CPU)", "mime": "audio/wav",
            "audio": base64.b64encode(audio).decode("ascii"),
            "url": f"/outputs/{output_path.name}",
        }

    audio = call_api("/audio/speech", {
        "model": SPEECH_MODEL, "voice": "coral", "input": text,
        "instructions": "Habla en español con voz cálida, natural y clara.",
    }, binary=True)
    audio_url = save_output(audio, "mp3")
    return {
        "provider": "openai", "model": SPEECH_MODEL, "mime": "audio/mpeg",
        "audio": base64.b64encode(audio).decode("ascii"), "url": audio_url,
    }


def prepare_chat(data: dict) -> tuple[str, str, list, str]:
    label = str(data.get("label", "")).strip()[:120]
    description = str(data.get("description", "")).strip()[:1500]
    question = str(data.get("message", "")).strip()[:6000]
    memory = str(data.get("memory", "")).strip()[:3000]
    history = data.get("history", [])
    if not label:
        raise APIError("Define una etiqueta para establecer el ámbito de la IA.")
    if not question:
        raise APIError("Escribe una consulta antes de enviar.")
    if not isinstance(history, list):
        history = []
    instructions = (
        "Eres Etiqueta, una IA útil y precisa que opera dentro de un ámbito definido por la persona. "
        "La etiqueta establece el tema y el objetivo de la conversación. Responde en el idioma del usuario, "
        "con claridad, rigor y atención al contexto y al historial. Si una petición parece relacionada, "
        "contéstala. Si su relación con el ámbito es ambigua, haz primero una pregunta breve para aclararla; "
        "rechaza solo cuando sea claramente ajena al ámbito, explicándolo amablemente y proponiendo una "
        "reformulación posible. No afirmes que has aprendido "
        "o cambiado tus parámetros de entrenamiento: puedes usar el contexto y las notas aportadas durante "
        "esta conversación. No inventes hechos ni capacidades. Puedes incluir una propuesta visual breve "
        "cuando ayude. Devuelve únicamente la respuesta final, sin etiquetas ni formato JSON."
    )
    prompt = (
        f"ÁMBITO / ETIQUETA: {label}\n"
        f"DESCRIPCIÓN DEL ÁMBITO: {description or 'Sin descripción adicional.'}\n"
        f"NOTAS DE CONTEXTO APORTADAS POR EL USUARIO: {memory or 'Ninguna.'}\n"
        f"CONSULTA ACTUAL:\n{question}"
    )
    return instructions, prompt, history, question


def normalize_reply(answer: str) -> tuple[str, bool]:
    image_tokens = bool(re.search(r"<(?:start_of_image|end_of_image|image|image_[^>]*)>", answer, re.IGNORECASE))
    answer = re.sub(r"<(?:start_of_image|end_of_image|image|image_[^>]*)>", "", answer,
                    flags=re.IGNORECASE).strip()
    if not answer:
        answer = "El modelo devolvió un marcador de imagen, no una imagen. Activa la opción «Imagen» para crearla con ComfyUI local."
    return answer, image_tokens


def generate_reply(data: dict) -> dict:
    instructions, prompt, history, _ = prepare_chat(data)
    if AI_PROVIDER == "openai":
        answer = make_openai_reply(instructions, prompt, history)
        model = OPENAI_TEXT_MODEL
    else:
        with MODEL_RESOURCE_LOCK:
            answer = make_ollama_reply(instructions, prompt, history,
                                       release_after=bool(data.get("image_requested", False)))
        model = OLLAMA_MODEL
    answer, image_tokens = normalize_reply(answer)
    return {"answer": answer, "model": model, "provider": AI_PROVIDER, "image_tokens": image_tokens}


class Handler(BaseHTTPRequestHandler):
    server_version = "EtiquetaIA/1.0"

    def send_sse(self, event: dict):
        payload = f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
        self.wfile.write(payload)
        self.wfile.flush()

    def stream_chat(self, data: dict):
        instructions, prompt, history, _ = prepare_chat(data)
        release_after = bool(data.get("image_requested", False))
        model = OLLAMA_MODEL if AI_PROVIDER == "ollama" else OPENAI_TEXT_MODEL
        try:
            if AI_PROVIDER != "ollama":
                self.send_json(200, {**generate_reply(data), "stream": False})
                return
            with MODEL_RESOURCE_LOCK:
                chunks = iter_ollama_reply(instructions, prompt, history, release_after=release_after)
                try:
                    first = next(chunks)
                except StopIteration:
                    self.send_json(200, {"answer": "", "model": model, "provider": AI_PROVIDER,
                                         "image_tokens": False, "stream": False})
                    return
                except APIError:
                    # Si el endpoint de streaming no está disponible, conserva el modo JSON.
                    answer = make_ollama_reply(instructions, prompt, history, release_after=release_after)
                    answer, image_tokens = normalize_reply(answer)
                    self.send_json(200, {"answer": answer, "model": model, "provider": AI_PROVIDER,
                                         "image_tokens": image_tokens, "stream": False})
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                collected = [first]
                self.send_sse({"token": first})
                try:
                    for part in chunks:
                        collected.append(part)
                        self.send_sse({"token": part})
                except APIError as exc:
                    self.send_sse({"error": str(exc)})
                    return
                answer, image_tokens = normalize_reply("".join(collected))
                self.send_sse({"done": True, "answer": answer, "model": model,
                               "provider": AI_PROVIDER, "image_tokens": image_tokens})
        except BrokenPipeError:
            pass
        except APIError as exc:
            self.send_json(502, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, status: int, value: dict):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY:
            raise APIError("La solicitud está vacía o supera el tamaño permitido.")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIError("El cuerpo de la solicitud no es JSON válido.") from exc
        if not isinstance(value, dict):
            raise APIError("El cuerpo de la solicitud debe ser un objeto JSON.")
        return value

    def do_GET(self):
        route = urllib.parse.urlsplit(self.path).path
        if route == "/api/status":
            if AI_PROVIDER == "openai":
                connected = bool(os.getenv("OPENAI_API_KEY", "").strip())
                detail = "OpenAI configurado" if connected else "Falta OPENAI_API_KEY"
            else:
                connected, detail = local_status(OLLAMA_BASE, "/api/tags", OLLAMA_KEY)
            image_ready, _ = local_status(COMFY_BASE, "/system_stats")
            self.send_json(200, {
                "configured": connected,
                "provider": AI_PROVIDER,
                "text_model": OPENAI_TEXT_MODEL if AI_PROVIDER == "openai" else OLLAMA_MODEL,
                "detail": detail,
                "image_ready": image_ready,
                "tts_provider": TTS_PROVIDER,
            })
            return

        if route.startswith("/api/image/"):
            job_id = route.removeprefix("/api/image/")
            if not re.fullmatch(r"[a-f0-9]{32}", job_id):
                self.send_error(404)
                return
            with IMAGE_JOBS_LOCK:
                job = IMAGE_JOBS.get(job_id)
                result = dict(job) if job else None
            if not result:
                self.send_error(404)
                return
            result.pop("created_at", None)
            self.send_json(200, result)
            return

        media_match = MEDIA_ROUTE.fullmatch(route)
        if media_match:
            filename = f"{media_match.group(1)}.{media_match.group(2)}"
            output_root = OUTPUTS_DIR.resolve()
            candidate = (output_root / filename).resolve()
            if (output_root.parent != ROOT.resolve() or candidate.parent != output_root
                    or not candidate.is_file()):
                self.send_error(404)
                return
            content_type = {"png": "image/png", "wav": "audio/wav", "mp3": "audio/mpeg"}[media_match.group(2)]
        else:
            allowed = STATIC_ROUTES.get(route)
            candidate = allowed.resolve() if allowed else None
            if (candidate is None or candidate.parent != ROOT.resolve()
                    or not candidate.is_file()):
                self.send_error(404)
                return
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
            }[candidate.suffix]

        if not candidate.is_file():
            self.send_error(404)
            return
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            data = self.read_json()
            route = urllib.parse.urlsplit(self.path).path
            if route == "/api/chat":
                if data.get("stream"):
                    self.stream_chat(data)
                else:
                    self.send_json(200, generate_reply(data))
            elif route == "/api/image":
                label = str(data.get("label", "")).strip()[:120]
                question = str(data.get("question", "")).strip()[:6000]
                answer = str(data.get("answer", "")).strip()[:6000]
                if not label or not question or not answer:
                    raise APIError("Falta la etiqueta, la pregunta o la respuesta para preparar la imagen.")
                job_id = start_image_job(label, question, answer)
                self.send_json(202, {"job_id": job_id, "status": "queued", "message": "Trabajo recibido"})
            elif route == "/api/speech":
                text = clean_speech_text(str(data.get("text", "")))
                if not text:
                    raise APIError("No hay texto para narrar.")
                self.send_json(200, generate_speech(text))
            else:
                self.send_error(404)
        except APIError as exc:
            self.send_json(502, {"error": str(exc)})
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            self.send_json(502, {"error": f"Respuesta inesperada del servicio: {exc}"})
        except BrokenPipeError:
            pass


def main():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"Etiqueta IA disponible en http://{host}:{port}")
    print(f"Proveedor de texto: {AI_PROVIDER} ({OLLAMA_MODEL if AI_PROVIDER != 'openai' else OPENAI_TEXT_MODEL})")
    print(f"Ollama: {OLLAMA_BASE} | ComfyUI: {COMFY_BASE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
