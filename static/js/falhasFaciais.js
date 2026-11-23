const facialFailureEndpoint = "/api/gestao/ocorrencias/falhas-faciais";
const stateLabels = {aberta:"Aberta",em_analise:"Em análise",resolvida:"Resolvida",descartada:"Descartada"};
let selectedOccurrenceId = null;
let pendingDecision = null;

async function facialFailureApi(url, options = {}) {
  const response = await fetch(url, {credentials:"same-origin", ...options, headers:{Accept:"application/json","Content-Type":"application/json",...(options.headers||{})}});
  let data = {};
  try { data = await response.json(); } catch (_error) {}
  if (response.status === 401) {
    window.top.location = "/login-page";
    throw new Error("Sessão expirada. Entre novamente.");
  }
  if (!response.ok) {
    const error = new Error(data.erro || "Não foi possível concluir a operação.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function displayValue(value) { return value || "Não informado"; }
function localDate(value) {
  return value ? new Intl.DateTimeFormat("pt-BR", {dateStyle:"short",timeStyle:"short",timeZone:"America/Sao_Paulo"}).format(new Date(value)) : "Não informado";
}
function filterParams() {
  const params = new URLSearchParams();
  [["busca","search-text"],["estado","state"],["unidade_id","unit"],["equipe_id","team"],["inicio","start"],["fim","end"]].forEach(([key,id]) => {
    const value = document.getElementById(id).value.trim();
    if (value) params.set(key, value);
  });
  return params;
}
function setPageError(message) {
  const node = document.getElementById("page-error");
  node.textContent = message || "";
  node.hidden = !message;
}
function updateFacialSelect(select) {
  const wrapper=select.closest(".custom-select");
  if(!wrapper)return;
  const selected=select.options[select.selectedIndex];
  const label=wrapper.querySelector(".select-label");
  if(selected&&label)label.textContent=selected.textContent;
  wrapper.querySelectorAll(".select-option").forEach(option=>{
    const isSelected=option.dataset.value===select.value;
    option.classList.toggle("selected",isSelected);
    option.setAttribute("aria-selected",String(isSelected));
  });
}
function syncFacialSelect(select) {
  const wrapper=select.closest(".custom-select");
  if(!wrapper)return;
  const menu=wrapper.querySelector(".select-menu");
  menu.replaceChildren();
  Array.from(select.options).forEach(option=>{
    const item=document.createElement("button");
    item.type="button";item.className="select-option";item.dataset.value=option.value;
    item.setAttribute("role","option");item.textContent=option.textContent;
    item.addEventListener("click",()=>{
      select.value=option.value;
      select.dispatchEvent(new Event("change",{bubbles:true}));
      updateFacialSelect(select);wrapper.classList.remove("open");
      wrapper.querySelector(".select-trigger").setAttribute("aria-expanded","false");
      wrapper.querySelector(".select-trigger").focus();
    });
    menu.appendChild(item);
  });
  updateFacialSelect(select);
}
function activateFacialSelect(select) {
  const wrapper=document.createElement("div");wrapper.className="custom-select";
  select.parentNode.insertBefore(wrapper,select);wrapper.appendChild(select);
  select.classList.add("native-select");
  const trigger=document.createElement("button");trigger.type="button";trigger.className="select-trigger";
  trigger.setAttribute("aria-haspopup","listbox");trigger.setAttribute("aria-expanded","false");
  trigger.innerHTML='<span class="select-label"></span><span class="select-chevron" aria-hidden="true"></span>';
  const menu=document.createElement("div");menu.className="select-menu";menu.setAttribute("role","listbox");
  menu.addEventListener("keydown",event=>{
    const options=[...menu.querySelectorAll(".select-option")],index=options.indexOf(document.activeElement);
    if(event.key==="Escape"){event.preventDefault();wrapper.classList.remove("open");trigger.setAttribute("aria-expanded","false");trigger.focus();}
    if(event.key==="ArrowDown"&&index<options.length-1){event.preventDefault();options[index+1]?.focus();}
    if(event.key==="ArrowUp"){event.preventDefault();if(index>0)options[index-1]?.focus();else trigger.focus();}
  });
  wrapper.insertBefore(trigger,select);wrapper.appendChild(menu);
  const open=()=>{
    document.querySelectorAll(".custom-select.open").forEach(item=>{if(item!==wrapper)item.classList.remove("open");});
    wrapper.classList.add("open");trigger.setAttribute("aria-expanded","true");
  };
  trigger.addEventListener("click",()=>{
    if(wrapper.classList.contains("open")){wrapper.classList.remove("open");trigger.setAttribute("aria-expanded","false");}
    else open();
  });
  trigger.addEventListener("keydown",event=>{
    if(event.key==="Escape"){wrapper.classList.remove("open");trigger.setAttribute("aria-expanded","false");}
    if(event.key==="ArrowDown"||event.key==="ArrowUp"){
      event.preventDefault();open();
      const options=menu.querySelectorAll(".select-option");
      (event.key==="ArrowUp"?options[options.length-1]:options[0])?.focus();
    }
  });
  select.addEventListener("change",()=>updateFacialSelect(select));
  syncFacialSelect(select);
}
function closeFacialSelects(event) {
  if(event.target.closest(".custom-select"))return;
  document.querySelectorAll(".custom-select.open").forEach(wrapper=>{
    wrapper.classList.remove("open");wrapper.querySelector(".select-trigger")?.setAttribute("aria-expanded","false");
  });
}
function populateOrganizationFilters(rows) {
  const unit = document.getElementById("unit"), team = document.getElementById("team");
  const units = new Map(), teams = new Map();
  rows.forEach(item => {
    if (item.unidade_id) units.set(item.unidade_id, item.unidade);
    if (item.equipe_id) teams.set(item.equipe_id, item.equipe);
  });
  [...units].sort((a,b) => a[1].localeCompare(b[1])).forEach(([id,name]) => unit.add(new Option(name,id)));
  [...teams].sort((a,b) => a[1].localeCompare(b[1])).forEach(([id,name]) => team.add(new Option(name,id)));
  syncFacialSelect(unit);syncFacialSelect(team);
}

async function loadFacialFailures(initial = false) {
  const body = document.getElementById("facial-failure-rows");
  body.innerHTML = '<tr><td colspan="6" class="empty">Carregando...</td></tr>';
  document.getElementById("table-count").textContent = "Carregando...";
  setPageError("");
  try {
    const suffix = initial ? "" : `?${filterParams()}`;
    const data = await facialFailureApi(`${facialFailureEndpoint}${suffix}`);
    if (initial) populateOrganizationFilters(data.ocorrencias);
    document.getElementById("result-count").textContent = data.ocorrencias.length;
    document.getElementById("table-count").textContent = `${data.ocorrencias.length} ${data.ocorrencias.length === 1 ? "ocorrência" : "ocorrências"}`;
    body.replaceChildren();
    if (!data.ocorrencias.length) {
      body.innerHTML = `<tr><td colspan="6" class="empty">${initial ? "Nenhuma ocorrência de falha facial." : "Nenhum resultado para os filtros informados."}</td></tr>`;
      return;
    }
    data.ocorrencias.forEach(item => {
      const row = document.createElement("tr");
      const employee=document.createElement("td"), employeeContent=document.createElement("div"), employeeName=document.createElement("strong"), employeeId=document.createElement("small");
      employeeContent.className="facial-employee"; employeeName.textContent=displayValue(item.funcionario); employeeId.textContent=displayValue(item.matricula); employeeContent.append(employeeName,employeeId); employee.appendChild(employeeContent); row.appendChild(employee);
      [
        `${displayValue(item.unidade)} / ${displayValue(item.equipe)}`,
      ].forEach(text => { const cell=document.createElement("td"); cell.textContent=text; row.appendChild(cell); });
      const state=document.createElement("td"), stateBadge=document.createElement("span"); stateBadge.className=`facial-state facial-state-${item.estado}`; stateBadge.textContent=stateLabels[item.estado] || item.estado; state.appendChild(stateBadge); row.appendChild(state);
      [localDate(item.primeira_ocorrencia_at),localDate(item.created_at)].forEach(text => { const cell=document.createElement("td"); cell.textContent=text; row.appendChild(cell); });
      const action=document.createElement("td"), button=document.createElement("button");
      button.type="button"; button.className="btn-primary"; button.textContent="Detalhar"; button.onclick=()=>openFacialFailureDetail(item.id);
      action.appendChild(button); row.appendChild(action); body.appendChild(row);
    });
  } catch (error) {
    document.getElementById("result-count").textContent = "—";
    document.getElementById("table-count").textContent = "Consulta indisponível";
    body.innerHTML = '<tr><td colspan="6" class="empty"></td></tr>';
    body.querySelector("td").textContent = error.message;
  }
}

async function openFacialFailureDetail(id) {
  setPageError("");
  try {
    const item = await facialFailureApi(`${facialFailureEndpoint}/${encodeURIComponent(id)}`);
    selectedOccurrenceId = id;
    const fields = [
      ["Funcionário",`${displayValue(item.funcionario)} · ${displayValue(item.matricula)}`],
      ["Estado",stateLabels[item.estado] || item.estado],
      ["Unidade",displayValue(item.unidade)], ["Equipe",displayValue(item.equipe)],
      ["Primeira tentativa",localDate(item.primeira_ocorrencia_at)], ["Criação",localDate(item.created_at)],
      ["Origem",item.origem === "automatica_falha_facial" ? "Automática — ciclo de falhas faciais" : displayValue(item.origem)],
      ["Responsável",displayValue(item.responsavel)], ["Decisão",displayValue(item.decisao)],
      ["Conclusão",localDate(item.resolved_at)], ["Descrição",displayValue(item.descricao)],
    ];
    const detail=document.getElementById("facial-failure-detail-content"); detail.replaceChildren();
    fields.forEach(([label,text]) => { const term=document.createElement("dt"), value=document.createElement("dd"); term.textContent=label; value.textContent=text; detail.append(term,value); });
    const audit=document.getElementById("facial-failure-audit"); audit.replaceChildren();
    if (!item.auditoria.length) {
      const empty=document.createElement("li"); empty.textContent="Nenhum evento de auditoria encontrado."; audit.appendChild(empty);
    } else item.auditoria.forEach(event => {
      const line=document.createElement("li"), time=document.createElement("small");
      const transition = event.estado_anterior && event.estado_novo ? `${stateLabels[event.estado_anterior] || event.estado_anterior} → ${stateLabels[event.estado_novo] || event.estado_novo}` : event.acao;
      line.textContent = `${transition} — ${displayValue(event.ator || "Sistema")}`;
      time.textContent = localDate(event.ocorrido_at); line.appendChild(time); audit.appendChild(line);
      if (event.justificativa) { const reason=document.createElement("small"); reason.textContent=`Justificativa: ${event.justificativa}`; line.appendChild(reason); }
    });
    const start=document.getElementById("start-review"), resolve=document.getElementById("resolve-occurrence"), discard=document.getElementById("discard-occurrence");
    start.hidden = item.estado !== "aberta";
    resolve.hidden = !["aberta","em_analise"].includes(item.estado);
    discard.hidden = !["aberta","em_analise"].includes(item.estado);
    document.getElementById("workflow-actions").hidden = ["resolvida","descartada"].includes(item.estado);
    const dialog=document.getElementById("facial-failure-detail"); if(!dialog.open)dialog.showModal();
  } catch (error) {
    if (error.status === 404) document.getElementById("facial-failure-detail").close();
    setPageError(error.message);
  }
}

async function startReview() {
  if (!selectedOccurrenceId) return;
  try {
    await facialFailureApi(`${facialFailureEndpoint}/${encodeURIComponent(selectedOccurrenceId)}/iniciar-analise`, {method:"POST",body:"{}"});
    await loadFacialFailures(false); await openFacialFailureDetail(selectedOccurrenceId);
  } catch (error) { await handleWorkflowError(error); }
}
function requestDecision(action) {
  pendingDecision = action;
  document.getElementById("decision-title").textContent = action === "resolver" ? "Resolver ocorrência" : "Descartar ocorrência";
  document.getElementById("decision-justification").value = "";
  document.getElementById("decision-error").textContent = "";
  document.getElementById("decision-dialog").showModal();
}
async function confirmDecision() {
  const justification=document.getElementById("decision-justification").value.trim();
  if (!justification) { document.getElementById("decision-error").textContent="Informe a justificativa."; return; }
  const label = pendingDecision === "resolver" ? "resolver" : "descartar";
  if (!window.confirm(`Confirma ${label} esta ocorrência? Esta ação não pode ser desfeita.`)) return;
  try {
    await facialFailureApi(`${facialFailureEndpoint}/${encodeURIComponent(selectedOccurrenceId)}/${pendingDecision}`, {method:"POST",body:JSON.stringify({justificativa})});
    document.getElementById("decision-dialog").close();
    await loadFacialFailures(false); await openFacialFailureDetail(selectedOccurrenceId);
  } catch (error) {
    document.getElementById("decision-error").textContent=error.message;
    await handleWorkflowError(error, error.status === 409);
  }
}
async function handleWorkflowError(error, showPageError = true) {
  if (error.status === 409) {
    const decisionDialog=document.getElementById("decision-dialog"); if(decisionDialog.open)decisionDialog.close();
    await loadFacialFailures(false); await openFacialFailureDetail(selectedOccurrenceId);
    if (showPageError) setPageError("A ocorrência foi alterada por outro usuário. Os dados foram atualizados.");
    return;
  }
  if (error.status === 403 || error.status === 404) {
    const detail=document.getElementById("facial-failure-detail"), decision=document.getElementById("decision-dialog");
    if(detail.open)detail.close(); if(decision.open)decision.close();
  }
  if (showPageError) setPageError(error.message);
}

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".facial-advanced-filters select").forEach(activateFacialSelect);
  document.addEventListener("click",closeFacialSelects);
  document.getElementById("search").addEventListener("click", () => loadFacialFailures(false));
  document.getElementById("refresh").addEventListener("click", () => loadFacialFailures(false));
  document.getElementById("toggle-filters").addEventListener("click", event => {
    const button=event.currentTarget, panel=document.getElementById("advanced-filters"), expanded=button.getAttribute("aria-expanded")==="true";
    button.setAttribute("aria-expanded",String(!expanded)); panel.hidden=expanded;
    button.innerHTML=expanded?'Gerenciar filtros <span aria-hidden="true">⌄</span>':'Ocultar filtros <span aria-hidden="true">⌃</span>';
  });
  document.getElementById("clear-filters").addEventListener("click", () => {
    document.getElementById("search-text").value="";
    ["state","unit","team"].forEach(id=>{const select=document.getElementById(id);select.value="";updateFacialSelect(select);});
    ["start","end"].forEach(id=>{const input=document.getElementById(id);if(input._flatpickr)input._flatpickr.clear();else input.value="";});
    loadFacialFailures(false);
  });
  document.getElementById("search-text").addEventListener("keydown", event => {if(event.key==="Enter"){event.preventDefault();loadFacialFailures(false);}});
  document.getElementById("start-review").addEventListener("click", startReview);
  document.getElementById("resolve-occurrence").addEventListener("click", () => requestDecision("resolver"));
  document.getElementById("discard-occurrence").addEventListener("click", () => requestDecision("descartar"));
  document.getElementById("confirm-decision").addEventListener("click", confirmDecision);
  await loadFacialFailures(true);
});
