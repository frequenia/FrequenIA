(() => {
  const form = document.getElementById('unit-form');
  const save = document.getElementById('unit-save');
  const rows = document.getElementById('unit-rows');
  const listStatus = document.getElementById('unit-list-status');
  const created = document.getElementById('unit-created');
  let listGeneration = 0;
  const locationLink = id => `/configuracoes?unidade=${encodeURIComponent(id)}#geofence-card`;
  function render(units) {
    rows.replaceChildren();
    if (!units.length) {
      const row = rows.insertRow(), cell = row.insertCell(); cell.colSpan = 5;
      cell.className = 'unit-empty'; cell.textContent = 'Nenhuma unidade cadastrada nesta empresa.'; return;
    }
    for (const unit of units) {
      const row = rows.insertRow();
      for (const text of [unit.nome, unit.codigo || '—', unit.timezone]) row.insertCell().textContent = text;
      const badge = document.createElement('span'); badge.className = `unit-state${unit.status === 'ativa' ? ' active' : ''}`;
      badge.textContent = unit.status === 'ativa' ? 'Ativa' : 'Inativa'; row.insertCell().append(badge);
      const locationCell = row.insertCell();
      if (unit.status !== 'ativa') { locationCell.textContent = 'Unidade inativa'; continue; }
      const link = document.createElement('a'); link.href = locationLink(unit.id);
      link.textContent = unit.endereco_geocodificado ? 'Ver endereço' : 'Configurar endereço';
      link.setAttribute('aria-label', `${link.textContent} — ${unit.nome}`); locationCell.append(link);
    }
  }
  async function load() {
    const generation = ++listGeneration;
    listStatus.dataset.state = ''; listStatus.textContent = 'Carregando unidades…';
    try {
      const response = await fetch('/api/admin/unidades');
      const result = await response.json();
      if (!response.ok) throw new Error(result.erro || 'Não foi possível carregar as unidades.');
      if (generation !== listGeneration) return;
      render(result.unidades); listStatus.textContent = `${result.unidades.length} ${result.unidades.length === 1 ? 'unidade cadastrada' : 'unidades cadastradas'} nesta empresa.`;
    } catch (error) {
      if (generation !== listGeneration) return;
      listStatus.dataset.state = 'error'; listStatus.textContent = error.message || 'Falha de conexão. Atualize a lista para tentar novamente.';
    }
  }
  document.getElementById('codigo').addEventListener('input', event => {
    const field = event.target;
    if (field.value !== field.value.toUpperCase()) field.value = field.value.toUpperCase();
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (save.disabled || !CadastroValidation.validate(form)) return;
    save.disabled = true; save.textContent = 'Cadastrando…'; created.hidden = true;
    try {
      const payload = Object.fromEntries(['nome', 'codigo', 'timezone', 'equipe_nome'].map(key => [key, document.getElementById(key).value.trim()]));
      const response = await fetch('/api/admin/unidades', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      const result = await response.json();
      if (!response.ok) { CadastroValidation.serverErrors(form, result); return; }
      form.reset();
      document.getElementById('unit-created-title').textContent = `Unidade ${result.unidade.nome} cadastrada`;
      document.getElementById('unit-configure').href = locationLink(result.unidade.id);
      created.hidden = false;
      await load();
    } catch (_) {
      CadastroValidation.serverErrors(form, {erro:'Não foi possível confirmar a resposta. Atualize a lista antes de cadastrar novamente.'});
    } finally { save.disabled = false; save.textContent = 'Cadastrar unidade'; }
  });
  document.getElementById('unit-refresh').addEventListener('click', load);
  load();
})();
