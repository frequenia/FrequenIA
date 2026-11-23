(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const photo = $('profile-photo'), placeholder = $('avatar-placeholder');
  const choose = $('photo-choose'), remove = $('photo-remove'), fileInput = $('photo-file');
  const dialog = $('photo-preview-dialog'), removal = $('photo-remove-dialog');
  let selected = null, previewURL = null, savedURL = null, busy = false;
  async function requestPhoto(options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      return await fetch('/api/perfil/foto', {credentials: 'same-origin', cache: 'no-store', ...options, signal: controller.signal});
    } catch (error) {
      if (error.name === 'AbortError') throw new TypeError('timeout');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  const token = document.querySelector('meta[name="profile-photo-token"]').content;
  function message(text, error = false) {
    $('photo-message').textContent = text;
    $('photo-message').dataset.state = error ? 'error' : 'success';
  }
  function setBusy(value) {
    busy = value;
    [choose, remove, $('photo-save'), $('photo-cancel'), $('photo-confirm-remove'), $('photo-keep')].forEach(button => { button.disabled = value; });
    $('profile-avatar').setAttribute('aria-busy', String(value));
  }
  function displayPhoto(blob) {
    if (savedURL) URL.revokeObjectURL(savedURL);
    savedURL = blob ? URL.createObjectURL(blob) : null;
    photo.hidden = !blob;
    placeholder.hidden = !!blob;
    remove.hidden = !blob;
    if (blob) photo.src = savedURL;
    else photo.removeAttribute('src');
    choose.setAttribute('aria-label', blob ? 'Trocar foto de perfil' : 'Adicionar foto de perfil');
  }
  async function loadPhoto() {
    const response = await requestPhoto();
    if (response.status === 204) return displayPhoto(null);
    if (!response.ok || !response.headers.get('Content-Type')?.startsWith('image/jpeg')) throw new Error();
    displayPhoto(await response.blob());
  }
  choose.addEventListener('click', () => { fileInput.value = ''; fileInput.click(); });
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024 || !file.size) {
      message('Escolha uma imagem JPG, PNG ou WebP de até 5 MB.', true);
      return;
    }
    selected = file;
    previewURL = URL.createObjectURL(file);
    $('photo-preview').src = previewURL;
    $('photo-preview-error').textContent = '';
    dialog.showModal();
  });
  dialog.addEventListener('close', () => {
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = null; selected = null;
    $('photo-preview').removeAttribute('src');
    choose.focus();
  });
  [dialog, removal].forEach(item => item.addEventListener('cancel', event => { if (busy) event.preventDefault(); }));
  $('photo-cancel').addEventListener('click', () => dialog.close());
  $('photo-save').addEventListener('click', async () => {
    if (busy || !selected) return;
    setBusy(true);
    $('photo-save').textContent = 'Salvando…';
    try {
      const response = await requestPhoto({ method: 'PUT', headers: { 'Content-Type': selected.type, 'X-Profile-Token': token }, body: selected });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.erro || 'Não foi possível salvar a foto. Tente novamente.');
      dialog.close();
      try { await loadPhoto(); message('Foto de perfil atualizada.'); }
      catch { message('Foto salva. Atualize a página para visualizar.', true); }
    } catch (error) {
      $('photo-preview-error').textContent = error instanceof TypeError ? 'Conexão interrompida. Atualize o perfil para verificar se a foto foi salva.' : error.message;
    } finally { setBusy(false); $('photo-save').textContent = 'Salvar foto'; }
  });
  remove.addEventListener('click', () => removal.showModal());
  $('photo-keep').addEventListener('click', () => removal.close());
  $('photo-confirm-remove').addEventListener('click', async () => {
    if (busy) return;
    setBusy(true);
    try {
      const response = await requestPhoto({ method: 'DELETE', headers: { 'X-Profile-Token': token } });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.erro || 'Não foi possível remover a foto.');
      displayPhoto(null); message('Foto de perfil removida.');
    } catch (error) { message(error instanceof TypeError ? 'Conexão interrompida. Atualize a página para conferir a foto.' : error.message, true); }
    finally { setBusy(false); removal.close(); choose.focus(); }
  });
  setBusy(true);
  loadPhoto().catch(() => message('Não foi possível carregar sua foto agora. Seus outros dados continuam disponíveis.', true)).finally(() => setBusy(false));
  window.addEventListener('pagehide', () => {
    if (savedURL) URL.revokeObjectURL(savedURL);
    if (previewURL) URL.revokeObjectURL(previewURL);
  });
})();
