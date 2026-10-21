const $ = (selector) => document.querySelector(selector);
const storeKey = 'etiqueta-ia-v1';
const defaults = { label: '', description: '', memory: '', history: [] };
let state = loadState();
let busy = false;
let toastTimer;
let speechRun = 0;

function loadState() {
  try { return { ...defaults, ...JSON.parse(localStorage.getItem(storeKey) || '{}') }; }
  catch { return { ...defaults }; }
}
function persist() {
  try { localStorage.setItem(storeKey, JSON.stringify(state)); }
  catch { showToast('El almacenamiento del navegador está lleno; los archivos siguen guardados en el servidor.'); }
}
function showToast(message) {
  const toast = $('#toast'); toast.textContent = message; toast.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 2800);
}
function updateScope() {
  state.label = $('#label-input').value.trim();
  state.description = $('#description-input').value.trim();
  $('#scope-preview-text').textContent = state.label || 'Tu etiqueta guiará cada respuesta.';
  $('#composer-label').textContent = state.label ? `#${state.label.toLocaleUpperCase()}` : 'ETIQUETA PENDIENTE';
  $('#chat-mode').textContent = state.label ? 'ÁMBITO PERSONALIZADO' : 'ESPERANDO TU ETIQUETA';
  $('#memory-count').textContent = state.memory.trim() ? '1' : '0';
}
function addMessage(role, content, { save = true, loading = false } = {}) {
  $('#welcome')?.remove();
  const wrapper = document.createElement('div'); wrapper.className = `message ${role}`;
  if (role === 'assistant') {
    const bubble = document.createElement('div'); bubble.className = 'bubble';
    if (loading) bubble.innerHTML = '<span class="loading-dots"><i></i><i></i><i></i></span>';
    else bubble.textContent = content;
    wrapper.innerHTML = '<div class="avatar">e.</div>';
    wrapper.append(bubble);
  } else {
    const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = content;
    wrapper.append(bubble);
  }
  $('#messages').append(wrapper); $('#messages').scrollTop = $('#messages').scrollHeight;
  if (save && !loading) {
    state.history.push({ role, content }); state.history = state.history.slice(-30); persist();
  }
  return wrapper;
}
function appendMedia(wrapper, item) {
  const bubble = wrapper.querySelector('.bubble');
  if (item.image) {
    const img = document.createElement('img'); img.className = 'reply-image';
    img.alt = `Ilustración para ${state.label}`; img.src = item.image; bubble.append(img);
    const link = document.createElement('a'); link.className = 'tool-button media-download';
    link.href = item.image; link.download = 'etiqueta-imagen.png'; link.textContent = '↓ Descargar imagen';
    bubble.append(link);
  }
  if (item.audio) {
    const audio = document.createElement('audio'); audio.className = 'reply-audio';
    audio.controls = true; audio.preload = 'none'; audio.src = item.audio; bubble.append(audio);
    const link = document.createElement('a'); link.className = 'tool-button media-download';
    link.href = item.audio; link.download = item.audio.endsWith('.mp3') ? 'etiqueta-voz.mp3' : 'etiqueta-voz.wav';
    link.textContent = '↓ Descargar audio'; bubble.append(link);
  }
}
function renderHistory() {
  if (!state.history.length) return;
  $('#welcome').remove();
  state.history.slice(-30).forEach(item => {
    const wrapper = addMessage(item.role === 'assistant' ? 'assistant' : 'user', item.content || '', { save:false });
    if (item.role === 'assistant' && (item.image || item.audio)) appendMedia(wrapper, item);
    if (item.role === 'assistant' && item.spoken && !item.audio) addSpeechAction(wrapper, item);
  });
}
async function postJSON(path, body) {
  const response = await fetch(path, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `La solicitud falló (${response.status}).`);
  return data;
}

async function streamChat(payload, bubble) {
  const response = await fetch('/api/chat', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ ...payload, stream:true }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || `La solicitud falló (${response.status}).`);
  }
  if (!response.headers.get('content-type')?.includes('text/event-stream')) {
    const data = await response.json(); bubble.textContent = data.answer || '';
    return data;
  }
  bubble.textContent = '';
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', finalData = {}, streamed = '';
  const readEvent = raw => {
    const line = raw.split('\n').find(value => value.startsWith('data:'));
    if (!line) return;
    const event = JSON.parse(line.slice(5).trim());
    if (event.error) throw new Error(event.error);
    if (event.token) { streamed += event.token; bubble.textContent = streamed; }
    if (event.done) { finalData = event; bubble.textContent = event.answer || streamed; }
  };
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream:!done }).replace(/\r/g, '');
    const events = buffer.split('\n\n'); buffer = events.pop();
    for (const event of events) readEvent(event);
    if (done) break;
  }
  if (buffer.trim()) readEvent(buffer);
  if (!finalData.answer && !streamed) throw new Error('El modelo no devolvió una respuesta.');
  return { ...finalData, answer:finalData.answer ?? streamed };
}

function imageProgressElement(bubble) {
  const holder = document.createElement('div'); holder.className = 'image-progress';
  const progress = document.createElement('progress'); progress.setAttribute('aria-label', 'Progreso de la imagen');
  const label = document.createElement('span'); label.textContent = 'Preparando imagen…';
  holder.append(progress, label); bubble.append(holder); return { holder, progress, label };
}
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
async function generateImage(answer, question, bubble, historyEntry, statusLabel) {
  const ui = imageProgressElement(bubble);
  try {
    const job = await postJSON('/api/image', { label:state.label, question, answer });
    let current;
    for (;;) {
      current = await fetch(`/api/image/${job.job_id}`).then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `No pude consultar la imagen (${response.status}).`);
        return data;
      });
      ui.label.textContent = current.message || 'ComfyUI está trabajando…';
      statusLabel.textContent = current.status === 'running' ? '▧ Generando imagen…' : '▧ Imagen en cola…';
      if (current.status === 'completed') break;
      if (current.status === 'error') throw new Error(current.error || 'ComfyUI no pudo generar la imagen.');
      await wait(900);
    }
    ui.holder.remove();
    historyEntry.image = current.image; persist(); appendMediaFromUrl(bubble, current.image, `Ilustración para ${state.label}`);
    statusLabel.textContent = '▧ Imagen local lista';
    return true;
  } catch (error) {
    ui.holder.remove();
    const note = document.createElement('p'); note.className = 'media-error';
    note.textContent = `No se pudo crear la imagen: ${error.message}`; bubble.append(note);
    const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'tool-button image-retry';
    retry.textContent = '↻ Reintentar imagen';
    retry.addEventListener('click', () => { note.remove(); retry.remove(); generateImage(answer, question, bubble, historyEntry, statusLabel); });
    bubble.append(retry);
    statusLabel.textContent = '▧ Error · puedes reintentar'; return false;
  }
}
function appendMediaFromUrl(bubble, url, alt) {
  const img = document.createElement('img'); img.className = 'reply-image'; img.alt = alt; img.src = url; bubble.append(img);
  const link = document.createElement('a'); link.className = 'tool-button media-download';
  link.href = url; link.download = 'etiqueta-imagen.png'; link.textContent = '↓ Descargar imagen'; bubble.append(link);
}

function cleanSpeech(text) {
  return String(text)
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/[>*_`~|]/g, ' ')
    .replace(/[\p{Extended_Pictographic}\uFE0F]/gu, ' ')
    .replace(/\s+/g, ' ').trim();
}
function spanishVoice() {
  const voices = speechSynthesis.getVoices();
  const lang = voice => String(voice.lang || '').toLowerCase().replace('_', '-');
  return voices.find(voice => lang(voice) === 'es-co')
    || voices.find(voice => ['es-mx','es-es'].includes(lang(voice)))
    || voices.find(voice => lang(voice).startsWith('es-'))
    || voices.find(voice => lang(voice) === 'es') || null;
}
function speechChunks(text, limit = 220) {
  const sentences = text.match(/[^.!?]+[.!?]+["'»)]*|[^.!?]+$/g) || [text];
  const chunks = [];
  for (const sentence of sentences.map(part => part.trim()).filter(Boolean)) {
    if (sentence.length <= limit) { chunks.push(sentence); continue; }
    let part = '';
    for (const word of sentence.split(/\s+/)) {
      if (part && `${part} ${word}`.length > limit) { chunks.push(part); part = word; }
      else part = part ? `${part} ${word}` : word;
    }
    if (part) chunks.push(part);
  }
  return chunks;
}
function speakInBrowser(text, button) {
  if (!('speechSynthesis' in window)) { button.disabled = false; showToast('Este navegador no incluye síntesis de voz.'); return; }
  const clean = cleanSpeech(text); const chunks = speechChunks(clean);
  if (!chunks.length) { button.disabled = false; showToast('No hay texto legible para narrar.'); return; }
  speechSynthesis.cancel(); const run = ++speechRun; const voice = spanishVoice(); let index = 0;
  const speakNext = () => {
    if (run !== speechRun || index >= chunks.length) { button.disabled = false; return; }
    const utterance = new SpeechSynthesisUtterance(chunks[index++]);
    utterance.lang = voice?.lang || 'es-CO'; if (voice) utterance.voice = voice;
    utterance.onend = speakNext;
    utterance.onerror = () => { if (run === speechRun) button.disabled = false; };
    speechSynthesis.speak(utterance);
  };
  button.disabled = true; speakNext();
}
function attachSavedAudio(bubble, url) {
  const audio = document.createElement('audio'); audio.className = 'reply-audio';
  audio.controls = true; audio.preload = 'none'; audio.src = url; bubble.append(audio);
  const link = document.createElement('a'); link.className = 'tool-button media-download';
  link.href = url; link.download = url.endsWith('.mp3') ? 'etiqueta-voz.mp3' : 'etiqueta-voz.wav';
  link.textContent = '↓ Descargar audio'; bubble.append(link);
  return audio;
}
async function generateSpeech(answer, button, bubble, historyEntry) {
  button.disabled = true;
  try {
    const data = await postJSON('/api/speech', { text:cleanSpeech(answer) });
    if (data.provider === 'browser') {
      historyEntry.spoken = true; persist(); speakInBrowser(answer,button); return;
    }
    historyEntry.audio = data.url; persist();
    const player = attachSavedAudio(bubble, data.url);
    player.play().catch(() => {});
    button.textContent = '◖ Reproducir'; button.disabled = false;
    button.onclick = () => player.play().catch(() => {});
  } catch (error) { button.disabled = false; showToast(`No se pudo generar la voz: ${error.message}`); }
}
function addSpeechAction(wrapper, historyEntry, tools = null) {
  const row = tools || document.createElement('div'); row.className = 'message-tools';
  const button = document.createElement('button'); button.className='tool-button'; button.textContent='◖ Escuchar';
  row.append(button);
  button.onclick=()=>generateSpeech(historyEntry.content,button,wrapper.querySelector('.bubble'),historyEntry);
  if (!tools) wrapper.after(row);
  return row;
}

async function submitMessage(message) {
  if (busy) return;
  state.label = $('#label-input').value.trim(); state.description = $('#description-input').value.trim();
  if (!state.label) { showToast('Primero define una etiqueta para tu espacio.'); $('#label-input').focus(); return; }
  busy = true; $('#send-button').disabled = true;
  addMessage('user', message);
  const pending = addMessage('assistant', '', { save:false, loading:true });
  const bubble = pending.querySelector('.bubble');
  try {
    const priorHistory = state.history.slice(0, -1);
    const imageRequested = $('#image-toggle').checked;
    const data = await streamChat({ label:state.label, description:state.description, memory:state.memory,
      message, history:priorHistory, image_requested:imageRequested }, bubble);
    const assistantEntry = { role:'assistant', content:data.answer, image:null, audio:null };
    state.history.push(assistantEntry); state.history = state.history.slice(-30); persist();
    if (data.image_tokens && !imageRequested) bubble.textContent += '\n\nEl modelo intentó representar una imagen con un marcador de texto. Activa «Imagen» para solicitar una imagen real a ComfyUI.';
    const tools = document.createElement('div'); tools.className = 'message-tools';
    if ($('#audio-toggle').checked) addSpeechAction(pending,assistantEntry,tools);
    let imageStatus;
    if (imageRequested) { imageStatus = document.createElement('span'); imageStatus.className='tool-button'; imageStatus.textContent='▧ Preparando imagen…'; tools.append(imageStatus); }
    if (tools.childElementCount) pending.after(tools);
    if (imageRequested) {
      // La imagen sigue en segundo plano; el usuario puede preparar otro mensaje.
      generateImage(data.answer,message,bubble,assistantEntry,imageStatus).catch(error => {
        console.error('Error de generación visual:', error);
      });
    }
    $('#messages').scrollTop = $('#messages').scrollHeight;
  } catch (error) {
    pending.remove(); addMessage('assistant', `No pude generar la respuesta. ${error.message}`, { save:false });
  } finally { busy = false; $('#send-button').disabled = false; $('#message-input').focus(); }
}

$('#label-input').value = state.label;
$('#description-input').value = state.description;
$('#memory-input').value = state.memory;
updateScope(); renderHistory();
$('#label-input').addEventListener('input', updateScope);
$('#description-input').addEventListener('input', updateScope);
$('#save-scope').addEventListener('click', () => { state.label=$('#label-input').value.trim(); state.description=$('#description-input').value.trim(); persist(); updateScope(); showToast(state.label ? 'Etiqueta guardada en este navegador.' : 'Escribe una etiqueta para guardar tu ámbito.'); });
$('#memory-toggle').addEventListener('click', () => $('#memory-dialog').showModal());
$('#save-memory').addEventListener('click', () => { state.memory=$('#memory-input').value.trim(); persist(); updateScope(); $('#memory-dialog').close(); showToast('Notas de memoria guardadas.'); });
$('#forget-memory').addEventListener('click', () => { state.memory=''; $('#memory-input').value=''; persist(); updateScope(); $('#memory-dialog').close(); showToast('Notas de memoria borradas.'); });
$('#new-chat').addEventListener('click', () => {
  state.history=[]; persist(); $('#messages').innerHTML='';
  $('#messages').append(Object.assign(document.createElement('div'),{id:'welcome',className:'welcome',innerHTML:'<div class="welcome-orbit"><span class="orbit-dot"></span><span class="orbit-center">e<span>.</span></span></div><span class="eyebrow">TU ESPACIO CREATIVO</span><h2>¿Qué te gustaría<br><em>imaginar hoy?</em></h2><p>Escribe una pregunta o un encargo creativo. Tu etiqueta mantiene cada idea dentro del mundo que elegiste.</p><div class="suggestions"><button class="suggestion" data-prompt="Ayúdame a empezar con tres ideas interesantes.">✳ &nbsp;Dame una idea para empezar</button><button class="suggestion" data-prompt="Crea una pequeña guía práctica para principiantes.">↗ &nbsp;Crea una guía breve</button></div>'}));
  wireSuggestions(); showToast('Conversación nueva.');
});
$('#clear-chat').addEventListener('click', () => $('#new-chat').click());
function wireSuggestions(){document.querySelectorAll('.suggestion').forEach(button=>button.addEventListener('click',()=>submitMessage(button.dataset.prompt)));}
wireSuggestions();
$('#chat-form').addEventListener('submit', event => { event.preventDefault(); const field=$('#message-input'); const message=field.value.trim(); if(!message)return; field.value=''; field.style.height='auto'; $('#char-count').textContent='0 / 6000'; submitMessage(message); });
$('#message-input').addEventListener('input', event => { const field=event.target; field.style.height='auto'; field.style.height=`${Math.min(field.scrollHeight,160)}px`; $('#char-count').textContent=`${field.value.length} / 6000`; });
$('#message-input').addEventListener('keydown', event => { if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('#chat-form').requestSubmit();} });
fetch('/api/status').then(response=>response.json()).then(status=>{
  $('#api-dot').classList.toggle('online',status.configured);
  $('#api-dot').title=status.configured?`${status.provider}: ${status.text_model} · Imagen ${status.image_ready?'local lista':'ComfyUI no conectado'} · Voz ${status.tts_provider}`:status.detail;
  $('#image-status').textContent=status.image_ready?'Generación local lista':'Inicia ComfyUI para generar imágenes';
  if (status.tts_provider === 'piper') document.querySelector('.audio-icon + span small').textContent='Voz local Piper en CPU';
}).catch(()=>{ $('#api-dot').title='Servidor desconectado'; $('#image-status').textContent='Servidor desconectado'; });
