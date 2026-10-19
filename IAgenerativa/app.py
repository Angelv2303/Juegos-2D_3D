"""Servidor local para Etiqueta IA, una experiencia multimodal acotada por contexto."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent


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


load_local_env()
OLLAMA_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "https://ollama.com" if OLLAMA_KEY else "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "gemma4:31b" if OLLAMA_KEY else "gemma3:4b")
COMFY_BASE = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188").rstrip("/")
COMFY_CHECKPOINT = os.getenv("COMFYUI_CHECKPOINT", "v1-5-pruned-emaonly-fp16.safetensors")
OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
SPEECH_MODEL = os.getenv("OPENAI_SPEECH_MODEL", "gpt-4o-mini-tts")
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()
MAX_BODY = 1_000_000


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
            return json.loads(response.read().decode("utf-8"))
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


def make_ollama_reply(instructions: str, prompt: str, history: list, *, release_after: bool = False) -> str:
    messages = [{"role": "system", "content": instructions}]
    for item in history[-8:]:
        if not isinstance(item, dict):
            continue
        role = "assistant" if item.get("role") == "assistant" else "user"
        content = str(item.get("content", ""))[:900]
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})
    result = request_json(OLLAMA_BASE, "/api/chat", {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.65},
        **({"keep_alive": 0} if release_after else {}),
    }, key=OLLAMA_KEY, timeout=240)
    return str(result.get("message", {}).get("content", "")).strip()


def make_openai_reply(instructions: str, prompt: str) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise APIError("Falta OPENAI_API_KEY. Cambia AI_PROVIDER=ollama para usar el modo local.")
    result = request_json(OPENAI_BASE, "/responses", {
        "model": OPENAI_TEXT_MODEL,
        "instructions": instructions,
        "input": prompt,
        "max_output_tokens": 1200,
    }, key=key)
    return str(result.get("output_text", "")).strip()


def make_local_image(prompt: str) -> dict:
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": COMFY_CHECKPOINT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "texto, letras, marca de agua, imagen borrosa, baja calidad", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": secrets.randbelow(2**32), "steps": 16, "cfg": 7, "sampler_name": "euler", "scheduler": "normal", "denoise": 1, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "Etiqueta", "images": ["6", 0]}},
    }
    queued = request_json(COMFY_BASE, "/prompt", {"prompt": workflow, "client_id": "etiqueta-ia"}, timeout=20)
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise APIError("ComfyUI no devolvió un identificador de generación.")
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        time.sleep(1)
        history = request_json(COMFY_BASE, f"/history/{urllib.parse.quote(prompt_id)}", timeout=20)
        record = history.get(prompt_id, {})
        images = [image for node in record.get("outputs", {}).values() for image in node.get("images", [])]
        if images:
            image = images[0]
            query = urllib.parse.urlencode({"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")})
            encoded = base64.b64encode(request_bytes(COMFY_BASE, f"/view?{query}", timeout=60)).decode("ascii")
            return {"image": f"data:image/png;base64,{encoded}", "model": "ComfyUI local"}
        if record.get("status", {}).get("status_str") == "error":
            raise APIError("ComfyUI no pudo generar la imagen. Revisa el checkpoint seleccionado.")
    raise APIError("ComfyUI tardó demasiado. Comprueba que el modelo local esté cargado.")


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


def generate_reply(data: dict) -> dict:
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
    context = "\n".join(
        f"{str(item.get('role', 'user'))[:10]}: {str(item.get('content', ''))[:900]}"
        for item in history[-8:]
        if isinstance(item, dict)
    )
    instructions = (
        "Eres Etiqueta, una IA útil y precisa que opera dentro de un ámbito definido por la persona. "
        "La etiqueta establece el tema y el objetivo de la conversación. Responde en el idioma del usuario, "
        "con claridad y rigor. Antes de contestar, determina si la petición se relaciona de forma razonable "
        "con el ámbito. Si no se relaciona, explica amablemente que queda fuera del ámbito configurado y "
        "ofrece una forma de reformularla dentro de él; no contestes la petición ajena al ámbito. "
        "Si la conexión no está clara, haz una pregunta breve para aclararla. No afirmes que has aprendido "
        "o cambiado tus parámetros de entrenamiento: puedes usar el contexto y las notas aportadas durante "
        "esta conversación. No inventes hechos ni capacidades. Puedes incluir una propuesta visual breve "
        "cuando ayude. Devuelve únicamente la respuesta final, sin etiquetas ni formato JSON."
    )
    prompt = (
        f"ÁMBITO / ETIQUETA: {label}\n"
        f"DESCRIPCIÓN DEL ÁMBITO: {description or 'Sin descripción adicional.'}\n"
        f"NOTAS DE CONTEXTO APORTADAS POR EL USUARIO: {memory or 'Ninguna.'}\n"
        f"CONVERSACIÓN RECIENTE:\n{context or 'Sin mensajes anteriores.'}\n\n"
        f"CONSULTA ACTUAL:\n{question}"
    )
    if AI_PROVIDER == "openai":
        answer = make_openai_reply(instructions, prompt)
        model = OPENAI_TEXT_MODEL
    else:
        answer = make_ollama_reply(
            instructions,
            prompt,
            history,
            release_after=bool(data.get("image_requested", False)),
        )
        model = OLLAMA_MODEL
    image_tokens = bool(re.search(r"<(?:start_of_image|end_of_image|image|image_[^>]*)>", answer, re.IGNORECASE))
    answer = re.sub(r"<(?:start_of_image|end_of_image|image|image_[^>]*)>", "", answer, flags=re.IGNORECASE).strip()
    if not answer:
        answer = "El modelo devolvió un marcador de imagen, no una imagen. Activa la opción «Imagen» para crearla con ComfyUI local."
    return {"answer": answer, "model": model, "provider": AI_PROVIDER, "image_tokens": image_tokens}


class Handler(BaseHTTPRequestHandler):
    server_version = "EtiquetaIA/1.0"

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
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIError("El cuerpo de la solicitud no es JSON válido.") from exc

    def do_GET(self):
        if self.path == "/api/status":
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
            })
            return
        relative = "index.html" if self.path in ("/", "/index.html") else self.path.lstrip("/")
        candidate = (ROOT / relative).resolve()
        if ROOT.resolve() not in candidate.parents or not candidate.is_file():
            self.send_error(404)
            return
        content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}.get(candidate.suffix, "application/octet-stream")
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
            if self.path == "/api/chat":
                self.send_json(200, generate_reply(data))
            elif self.path == "/api/image":
                prompt = str(data.get("prompt", "")).strip()[:3000]
                if not prompt:
                    raise APIError("Escribe una descripción para crear la imagen.")
                self.send_json(200, make_local_image(prompt))
            elif self.path == "/api/speech":
                text = str(data.get("text", "")).strip()[:4000]
                if not text:
                    raise APIError("No hay texto para narrar.")
                audio = call_api("/audio/speech", {"model": SPEECH_MODEL, "voice": "coral", "input": text, "instructions": "Habla en español con voz cálida, natural y clara."}, binary=True)
                self.send_json(200, {"audio": base64.b64encode(audio).decode("ascii"), "mime": "audio/mpeg", "model": SPEECH_MODEL})
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
