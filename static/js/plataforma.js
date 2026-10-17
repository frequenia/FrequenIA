const message = document.getElementById("page-message");
const companySelect = document.getElementById("company-select");

function showMessage(text) {
  message.textContent = text;
  message.hidden = !text;
}

function value(value, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function localDate(valueToFormat) {
  return valueToFormat ? new Date(valueToFormat).toLocaleString("pt-BR") : "—";
}

function clearRows(body, columns, label) {
  body.replaceChildren();
  const row = body.insertRow();
  const cell = row.insertCell();
  cell.colSpan = columns;
  cell.textContent = label;
}

async function request(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.erro || "Não foi possível carregar os dados.");
  return body;
}

async function loadSummary() {
  const { resumo } = await request("/api/plataforma/resumo");
  document.getElementById("companies-total").textContent = value(resumo.empresas_total, "0");
  document.getElementById("companies-status").textContent = `${resumo.empresas_ativas} ativas · ${resumo.empresas_inativas} inativas`;
  document.getElementById("employees-active").textContent = value(resumo.funcionarios_ativos, "0");
  document.getElementById("terminals-active").textContent = value(resumo.terminais_ativos, "0");
  document.getElementById("terminals-status").textContent = `${resumo.terminais_revogados} revogados`;
  document.getElementById("pending-access").textContent = value(resumo.primeiros_acessos_pendentes, "0");
}

async function loadCompanies() {
  const selected = companySelect.value;
  const requested = new URLSearchParams(window.location.search).get("empresa");
  const companies = await request("/listarEmpresas");
  companySelect.replaceChildren(new Option("Selecione uma empresa", ""));
  companies.forEach((company) => companySelect.add(new Option(`${company.nome} · ${company.status}`, company.id)));
  const target = requested || selected;
  if (companies.some((company) => company.id === target)) companySelect.value = target;
}

function renderCounts(counts) {
  const fields = [
    ["Unidades", counts.unidades], ["Equipes", counts.equipes],
    ["Funcionários", counts.funcionarios], ["Funcionários ativos", counts.funcionarios_ativos],
    ["Terminais", counts.terminais], ["Terminais ativos", counts.terminais_ativos],
  ];
  const container = document.getElementById("company-counts");
  container.replaceChildren();
  fields.forEach(([label, count]) => {
    const card = document.createElement("div"); card.className = "mini-card";
    const title = document.createElement("span"); title.textContent = label;
    const number = document.createElement("strong"); number.textContent = value(count, "0");
    card.append(title, number); container.append(card);
  });
}

function renderAdministrators(companyId, administrators) {
  const body = document.getElementById("admins-body");
  body.replaceChildren();
  if (!administrators.length) return clearRows(body, 5, "Nenhum administrador da empresa cadastrado.");
  administrators.forEach((administrator) => {
    const row = body.insertRow();
    [administrator.nome, administrator.email, administrator.matricula,
      administrator.primeiro_acesso_pendente ? "Primeiro acesso pendente" : administrator.status]
      .forEach((item) => { const cell = row.insertCell(); cell.textContent = value(item); });
    const actionCell = row.insertCell();
    const button = document.createElement("button");
    button.type = "button"; button.className = "small-action";
    button.textContent = "Reenviar convite"; button.disabled = !administrator.primeiro_acesso_pendente;
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await request(`/api/plataforma/empresas/${companyId}/administradores/${administrator.id}/reenviar-convite`, { method: "POST" });
        showMessage(result.mensagem);
        await loadAudit();
      } catch (error) { showMessage(error.message); button.disabled = false; }
    });
    actionCell.append(button);
  });
}

function renderTerminals(terminals) {
  const body = document.getElementById("terminals-body");
  body.replaceChildren();
  if (!terminals.length) return clearRows(body, 4, "Nenhum terminal cadastrado.");
  terminals.forEach((terminal) => {
    const row = body.insertRow();
    [terminal.nome, terminal.status, localDate(terminal.created_at), localDate(terminal.revoked_at)]
      .forEach((item) => { const cell = row.insertCell(); cell.textContent = value(item); });
  });
}

async function loadCompanyDetail() {
  const companyId = companySelect.value;
  document.getElementById("company-empty").hidden = Boolean(companyId);
  document.getElementById("company-detail").hidden = !companyId;
  if (!companyId) return;
  const detail = await request(`/api/plataforma/empresas/${companyId}`);
  document.getElementById("company-name").textContent = detail.empresa.nome;
  document.getElementById("company-document").textContent = `CNPJ ${value(detail.empresa.cnpj)} · criada em ${localDate(detail.empresa.created_at)}`;
  const status = document.getElementById("company-status");
  status.textContent = detail.empresa.status; status.classList.toggle("inactive", detail.empresa.status !== "ativa");
  renderCounts(detail.contadores);
  renderAdministrators(companyId, detail.administradores);
  renderTerminals(detail.terminais);
}

async function loadAudit() {
  const { auditoria } = await request("/api/plataforma/auditoria?limite=50");
  const body = document.getElementById("audit-body"); body.replaceChildren();
  if (!auditoria.length) return clearRows(body, 4, "Nenhuma ação de plataforma registrada.");
  auditoria.forEach((event) => {
    const row = body.insertRow();
    [localDate(event.ocorrido_at), event.acao, event.empresa, event.ator]
      .forEach((item) => { const cell = row.insertCell(); cell.textContent = value(item); });
  });
}

async function loadAll() {
  showMessage("");
  try { await Promise.all([loadSummary(), loadCompanies(), loadAudit()]); await loadCompanyDetail(); }
  catch (error) { showMessage(error.message); }
}

companySelect.addEventListener("change", () => loadCompanyDetail().catch((error) => showMessage(error.message)));
document.getElementById("refresh").addEventListener("click", loadAll);
loadAll();
