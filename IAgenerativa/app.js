const $ = (selector) => document.querySelector(selector);
const storeKey = 'etiqueta-ia-v1';
const defaults = { label: '', description: '', memory: '', history: [] };
let state = loadState();
let busy = false;
let toastTimer;

function loadState() {
  try { return { ...defaults, ...JSON.parse(localStorage.getItem(storeKey) || '{}') }; }
  catch { return { ...defaults }; }
}
function persist() { localStorage.setItem(storeKey, JSON.stringify(state)); }
function showToast(message) {
  const toast = $('#toast'); toast.textContent = message; toast.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 2800);
}
function safeText(text) { return String(text).replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[char]); }
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
  if (role === 'assistant') wrapper.innerHTML = `<div class="avatar">e.</div><div class="bubble">${loading ? '<span class="loading-dots"><i></i><i></i><i></i></span>' : safeText(content)}</div>`;
  else wrapper.innerHTML = `<div class="bubble">${safeText(content)}</div>`;
  $('#messages').append(wrapper); $('#messages').scrollTop = $('#messages').scrollHeight;
  if (save && !loading) { state.history.push({ role, content }); state.history = state.history.slice(-30); persist(); }
  return wrapper;
}
function renderHistory() {
  if (!state.history.length) return;
  $('#welcome').remove();
  state.history.slice(-30).forEach(item => addMessage(item.role === 'assistant' ? 'assistant' : 'user', item.content, { save:false }));
}
async function postJSON(path, body) {
  const response = await fetch(path, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `La solicitud falló (${response.status}).`);
  return data;
}
async function generateImage(answer, question, bubble) {
  const prompt = `Crea una ilustración visual pertinente para el siguiente ámbito, sin letras ni texto incrustado. Ámbito: ${state.label}. Contexto: ${state.description || 'creativo y educativo'}. Petición: ${question}. Respuesta de referencia: ${answer.slice(0, 900)}. Usa una composición clara, atractiva y coherente con la petición.`;
  const holder = document.createElement('div'); holder.className = 'loading-dots'; holder.setAttribute('aria-label','Creando imagen'); holder.innerHTML = '<i></i><i></i><i></i>'; bubble.append(holder);
  try { const data = await postJSON('/api/image', { prompt }); const img = document.createElement('img'); img.className = 'reply-image'; img.alt = `Ilustración para ${state.label}`; img.src = data.image; holder.replaceWith(img); return true; }
  catch (error) { holder.replaceWith(document.createTextNode(`\nNo se pudo crear la imagen: ${error.message}`)); return false; }
}
async function generateSpeech(answer, button) {
  if (!('speechSynthesis' in window)) { showToast('Este navegador no incluye síntesis de voz.'); return; }
  const utterance = new SpeechSynthesisUtterance(answer); utterance.lang = 'es';
  speechSynthesis.cancel(); speechSynthesis.speak(utterance);
  button.textContent = '◖ Reproducir de nuevo'; button.disabled = false;
  button.onclick = () => { speechSynthesis.cancel(); speechSynthesis.speak(utterance); };
}
async function submitMessage(message) {
  if (busy) return;
  state.label = $('#label-input').value.trim(); state.description = $('#description-input').value.trim();
  if (!state.label) { showToast('Primero define una etiqueta para tu espacio.'); $('#label-input').focus(); return; }
  busy = true; $('#send-button').disabled = true;
  addMessage('user', message);
  const pending = addMessage('assistant', '', { save:false, loading:true });
  try {
    const priorHistory = state.history.slice(0, -1);
    const imageRequested = $('#image-toggle').checked;
    const data = await postJSON('/api/chat', { label:state.label, description:state.description, memory:state.memory, message, history:priorHistory, image_requested:imageRequested });
    state.history.push({ role:'assistant', content:data.answer }); state.history = state.history.slice(-30); persist();
    const bubble = pending.querySelector('.bubble'); bubble.textContent = data.answer;
    if (data.image_tokens && !imageRequested) bubble.textContent += '\n\nEl modelo intentó representar una imagen con un marcador de texto. Activa «Imagen» para solicitar una imagen real a ComfyUI.';
    const tools = document.createElement('div'); tools.className = 'message-tools';
    if ($('#audio-toggle').checked) { const button = document.createElement('button'); button.className='tool-button'; button.textContent='◖ Escuchar'; tools.append(button); button.onclick=()=>generateSpeech(data.answer,button); }
    let imageStatus;
    if (imageRequested) { imageStatus = document.createElement('span'); imageStatus.className='tool-button'; imageStatus.textContent='▧ Creando imagen local…'; tools.append(imageStatus); }
    if (tools.childElementCount) pending.after(tools);
    if (imageRequested) imageStatus.textContent = await generateImage(data.answer,message,bubble) ? '▧ Imagen local lista' : '▧ No disponible';
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
$('#new-chat').addEventListener('click', () => { state.history=[]; persist(); $('#messages').innerHTML=''; $('#messages').append(Object.assign(document.createElement('div'),{id:'welcome',className:'welcome',innerHTML:'<div class="welcome-orbit"><span class="orbit-dot"></span><span class="orbit-center">e<span>.</span></span></div><span class="eyebrow">TU ESPACIO CREATIVO</span><h2>¿Qué te gustaría<br><em>imaginar hoy?</em></h2><p>Escribe una pregunta o un encargo creativo. Tu etiqueta mantiene cada idea dentro del mundo que elegiste.</p><div class="suggestions"><button class="suggestion" data-prompt="Ayúdame a empezar con tres ideas interesantes.">✳ &nbsp;Dame una idea para empezar</button><button class="suggestion" data-prompt="Crea una pequeña guía práctica para principiantes.">↗ &nbsp;Crea una guía breve</button></div>'})); wireSuggestions(); showToast('Conversación nueva.'); });
$('#clear-chat').addEventListener('click', () => $('#new-chat').click());
function wireSuggestions(){document.querySelectorAll('.suggestion').forEach(button=>button.addEventListener('click',()=>submitMessage(button.dataset.prompt)));}
wireSuggestions();
$('#chat-form').addEventListener('submit', event => { event.preventDefault(); const field=$('#message-input'); const message=field.value.trim(); if(!message)return; field.value=''; field.style.height='auto'; $('#char-count').textContent='0 / 6000'; submitMessage(message); });
$('#message-input').addEventListener('input', event => { const field=event.target; field.style.height='auto'; field.style.height=`${Math.min(field.scrollHeight,160)}px`; $('#char-count').textContent=`${field.value.length} / 6000`; });
$('#message-input').addEventListener('keydown', event => { if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('#chat-form').requestSubmit();} });
fetch('/api/status').then(response=>response.json()).then(status=>{ $('#api-dot').classList.toggle('online',status.configured); $('#api-dot').title=status.configured?`${status.provider}: ${status.text_model} · Imagen ${status.image_ready?'local lista':'ComfyUI no conectado'}`:status.detail; $('#image-status').textContent=status.image_ready?'Generación local lista':'Inicia ComfyUI para generar imágenes'; }).catch(()=>{ $('#api-dot').title='Servidor desconectado'; $('#image-status').textContent='Servidor desconectado'; });
