let selectedId = null;
let appliedParams = new URLSearchParams();
let appliedExtra = {};
let availableReasons = [];
const labels = {esquecimento_marcacao:"Esquecimento de marcação",horario_incorreto:"Horário incorreto",tipo_incorreto:"Tipo incorreto",justificativa:"Justificativa",outro:"Outro"};
const statusLabels = {pendente_gestor:"Pendente com gestor",solicitada:"Pendente com gestor",em_analise_gestor:"Pendente com gestor",encaminhada_rh:"Em análise pelo RH",em_analise_rh:"Em análise pelo RH",aprovada:"Aprovada",rejeitada:"Rejeitada",cancelada:"Cancelada"};

class ApiError extends Error { constructor(message,status){super(message);this.status=status;} }

async function api(url, options={}) {
  const response = await fetch(url, {credentials:"same-origin", ...options, headers:{"Content-Type":"application/json", ...(options.headers||{})}});
  let data={}; try{data=await response.json();}catch(_error){}
  if(!response.ok) throw new ApiError(data.erro || "Não foi possível concluir a operação.",response.status);
  return data;
}
function value(value){return value || "Não informado";}
function localDate(value){return value ? new Intl.DateTimeFormat("pt-BR",{dateStyle:"short",timeStyle:"short",timeZone:"America/Sao_Paulo"}).format(new Date(value)) : "Não informado";}

function syncSelect(select){
  const wrapper=select.closest(".custom-select");
  if(!wrapper)return;
  const menu=wrapper.querySelector(".select-menu");
  menu.replaceChildren();
  Array.from(select.options).forEach(option=>{
    const item=document.createElement("button");
    item.type="button";
    item.className="select-option";
    item.dataset.value=option.value;
    item.setAttribute("role","option");
    item.textContent=option.textContent;
    item.onclick=()=>{
      select.value=option.value;
      select.dispatchEvent(new Event("change",{bubbles:true}));
      wrapper.classList.remove("open");
      const input=wrapper.querySelector(".name-search");
      if(input){input.value=option.value?option.textContent:"";input.setAttribute("aria-expanded","false");input.focus();wrapper.classList.remove("open");}
    };
    menu.appendChild(item);
  });
  updateSelect(select);
}
function updateSelect(select){
  const wrapper=select.closest(".custom-select");
  if(!wrapper)return;
  const selected=select.options[select.selectedIndex];
  const input=wrapper.querySelector(".name-search");
  const label=wrapper.querySelector(".select-label");
  if(selected && input && document.activeElement!==input) input.value=selected.value?selected.textContent:"";
  if(selected && label) label.textContent=selected.textContent;
  wrapper.querySelectorAll(".select-option").forEach(item=>item.classList.toggle("selected",item.dataset.value===select.value));
}
function customSelect(select){
  if(select.closest(".custom-select"))return;
  const wrapper=document.createElement("div");
  wrapper.className="custom-select";
  select.parentNode.insertBefore(wrapper,select);
  wrapper.appendChild(select);
  select.classList.add("native-select");
  const searchable=["employee","reviewer"].includes(select.id);
  const trigger=document.createElement(searchable?"input":"button");
  if(searchable){
    trigger.type="search";
    trigger.className="select-trigger name-search";
    trigger.placeholder=select.id==="employee"?"Buscar por nome ou matrícula":"Buscar responsável";
    trigger.setAttribute("aria-label",trigger.placeholder);
    trigger.setAttribute("role","combobox");
    trigger.setAttribute("aria-autocomplete","list");
    trigger.setAttribute("aria-expanded","false");
    trigger.autocomplete="off";
  }else{
    trigger.type="button";
    trigger.className="select-trigger";
    trigger.setAttribute("aria-haspopup","listbox");
    trigger.innerHTML='<span class="select-label"></span><span class="select-chevron" aria-hidden="true"></span>';
  }
  const menu=document.createElement("div");
  menu.className="select-menu";
  menu.setAttribute("role","listbox");
  wrapper.insertBefore(trigger,select);
  wrapper.appendChild(menu);
  function open(){
    document.querySelectorAll(".custom-select.open").forEach(item=>{if(item!==wrapper)item.classList.remove("open");});
    wrapper.classList.add("open");
    if(searchable) trigger.setAttribute("aria-expanded","true");
  }
  if(searchable){
    trigger.addEventListener("focus",()=>{menu.querySelectorAll(".select-option").forEach(item=>{item.hidden=false;});open();});
    trigger.addEventListener("click",()=>{menu.querySelectorAll(".select-option").forEach(item=>{item.hidden=false;});open();});
    trigger.addEventListener("input",()=>{
      open();
      const term=normalizeText(trigger.value);
      menu.querySelectorAll(".select-option").forEach(item=>{
        item.hidden=Boolean(term)&&!normalizeText(item.textContent).includes(term);
      });
    });
    trigger.addEventListener("keydown",event=>{
      if(event.key==="Escape"){wrapper.classList.remove("open");trigger.setAttribute("aria-expanded","false");trigger.blur();}
      if(event.key==="ArrowDown"){event.preventDefault();open();menu.querySelector(".select-option:not([hidden])")?.focus();}
    });
    wrapper.addEventListener("focusout",()=>{
      setTimeout(()=>{
        if(!wrapper.contains(document.activeElement)){
          wrapper.classList.remove("open");
          trigger.setAttribute("aria-expanded","false");
          updateSelect(select);
        }
      },0);
    });
  }else{
    trigger.onclick=()=>{if(wrapper.classList.contains("open"))wrapper.classList.remove("open");else open();};
  }
  select.addEventListener("change",()=>updateSelect(select));
  syncSelect(select);
}
function activateSelects(){document.querySelectorAll(".filter-card select").forEach(customSelect);if(!document.body.dataset.selectListener){document.body.dataset.selectListener="1";document.addEventListener("click",event=>{if(!event.target.closest(".custom-select"))document.querySelectorAll(".custom-select.open").forEach(item=>item.classList.remove("open"));});}}

async function loadEmployees(){
  const rows=await api("/api/gestao/funcionarios"); const select=document.getElementById("employee");
  rows.forEach(item=>select.add(new Option(`${item.nome} - ${item.matricula}`,item.funcionario_id))); syncSelect(select);
}
function params(){
  const result=new URLSearchParams();
  [["funcionario_id","employee"],["status","status"],["tipo","type"],["inicio","start"],["fim","end"]].forEach(([key,id])=>{const v=document.getElementById(id).value;if(v)result.set(key,v);});
  return result;
}
function initializeDateRange(){
  if(!window.flatpickr)return;
  const start=document.getElementById("start"),end=document.getElementById("end");
  const today=new Date();
  const monthStart=new Date(today.getFullYear(),today.getMonth(),1);
  const formatDate=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
  const options={dateFormat:"Y-m-d",altInput:true,altFormat:"d/m/Y",locale:"pt",disableMobile:true,monthSelectorType:"static"};
  const startCalendar=window.flatpickr(start,options);
  const endCalendar=window.flatpickr(end,options);
  if(!start.value)startCalendar.setDate(formatDate(monthStart),false);
  if(!end.value)endCalendar.setDate(formatDate(today),false);
}
function populateFilter(id, values) {
  const select=document.getElementById(id);
  const current=select.value;
  while(select.options.length > (id==="reviewer" ? 2 : 1)) select.remove(select.options.length-1);
  [...new Set(values.filter(Boolean))].sort((a,b)=>a.localeCompare(b,"pt-BR")).forEach(item=>select.add(new Option(item,item)));
  select.value=[...select.options].some(option=>option.value===current)?current:"";
  syncSelect(select);
}
function normalizeText(text) {
  return String(text||"").normalize("NFD").replace(/\p{M}/gu,"").toLowerCase().trim();
}
function updateReasonOptions() {
  const input=document.getElementById("reason-filter");
  const menu=document.getElementById("reason-options");
  const term=normalizeText(input.value);
  const matches=availableReasons.filter(reason=>normalizeText(reason).includes(term));
  menu.replaceChildren();
  if(!matches.length){
    const empty=document.createElement("div");
    empty.className="reason-empty";
    empty.textContent="Nenhum motivo encontrado.";
    menu.appendChild(empty);
  }
  matches.forEach(reason=>{
    const button=document.createElement("button");
    button.type="button";
    button.className="select-option";
    button.setAttribute("role","option");
    button.textContent=reason;
    button.addEventListener("click",()=>{
      input.value=reason;
      menu.hidden=true;
      input.setAttribute("aria-expanded","false");
      input.focus();
    });
    menu.appendChild(button);
  });
}
function setupReasonFilter() {
  const input=document.getElementById("reason-filter");
  const menu=document.getElementById("reason-options");
  function open() {
    updateReasonOptions();
    menu.hidden=false;
    input.setAttribute("aria-expanded","true");
  }
  input.addEventListener("focus",open);
  input.addEventListener("click",open);
  input.addEventListener("input",open);
  input.addEventListener("keydown",event=>{
    if(event.key==="Escape"){menu.hidden=true;input.setAttribute("aria-expanded","false");}
    if(event.key==="ArrowDown"&&!menu.hidden){event.preventDefault();menu.querySelector("button")?.focus();}
  });
  document.addEventListener("click",event=>{
    if(!event.target.closest(".reason-filter")){menu.hidden=true;input.setAttribute("aria-expanded","false");}
  });
}
function renderRail(rows) {
  const oldest=document.getElementById("oldest-requests");
  const categories=document.getElementById("request-categories");
  const operationalTitle=document.getElementById("operational-title");
  const operationalDetail=document.getElementById("operational-detail");
  oldest.replaceChildren();
  categories.replaceChildren();
  const pending=rows.filter(item=>["pendente_gestor","solicitada","em_analise_gestor","encaminhada_rh","em_analise_rh"].includes(item.status)&&item.criada_em)
    .sort((a,b)=>new Date(a.criada_em)-new Date(b.criada_em)).slice(0,3);
  const awaitingManager=rows.filter(item=>["pendente_gestor","solicitada","em_analise_gestor"].includes(item.status)).length;
  operationalTitle.textContent=awaitingManager ? `${awaitingManager} ${awaitingManager===1?"solicitação pendente":"solicitações pendentes"}` : "Nenhuma solicitação pendente";
  operationalDetail.textContent=awaitingManager ? "Aguardando análise do gestor na consulta atual." : "As solicitações desta consulta estão em análise ou concluídas.";
  if(!pending.length) oldest.textContent="Nenhuma solicitação pendente nesta consulta.";
  pending.forEach(item=>{
    const button=document.createElement("button");
    button.type="button";
    button.className="occ-rail-item";
    const icon=document.createElement("span");
    icon.className="occ-request-icon";
    icon.setAttribute("aria-hidden","true");
    icon.innerHTML='<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3"/><path d="M5 20v-1a7 7 0 0 1 14 0v1"/></svg>';
    const content=document.createElement("span");
    content.className="occ-request-content";
    const name=document.createElement("strong");
    name.textContent=value(item.funcionario);
    const info=document.createElement("span");
    const days=Math.max(0,Math.floor((Date.now()-new Date(item.criada_em).getTime())/86400000));
    info.textContent=`${labels[item.tipo]||item.tipo} · ${days===0?"Aberta hoje":`há ${days} ${days===1?"dia":"dias"}`}`;
    content.append(name,info);
    const arrow=document.createElement("span");
    arrow.className="occ-request-arrow";
    arrow.setAttribute("aria-hidden","true");
    arrow.textContent="›";
    button.append(icon,content,arrow);
    button.addEventListener("click",()=>openDetail(item.id));
    oldest.append(button);
  });
  const counts=new Map();
  rows.forEach(item=>counts.set(item.tipo,(counts.get(item.tipo)||0)+1));
  if(!counts.size) categories.textContent="Nenhuma solicitação nesta consulta.";
  [...counts.entries()].sort((a,b)=>b[1]-a[1]||(labels[a[0]]||a[0]).localeCompare(labels[b[0]]||b[0],"pt-BR")).forEach(([type,count])=>{
    const line=document.createElement("div");
    line.className="occ-category";
    const name=document.createElement("span");
    name.className="occ-category-name";
    const dot=document.createElement("span");
    dot.className="occ-category-dot";
    dot.setAttribute("aria-hidden","true");
    name.appendChild(dot);
    const label=document.createElement("span");
    label.textContent=labels[type]||type;
    name.appendChild(label);
    const number=document.createElement("strong");
    number.textContent=`${count} · ${Math.round(count / rows.length * 100)}%`;
    line.append(name,number);
    categories.append(line);
  });
}
async function load(){
  const tbody=document.getElementById("rows"); tbody.innerHTML='<tr><td colspan="6" class="empty">Carregando...</td></tr>';
  document.getElementById("oldest-requests").textContent="Carregando...";
  document.getElementById("request-categories").textContent="Carregando...";
  try{
    const query=new URLSearchParams(appliedParams);query.delete("status");
    const data=await api(`/api/gestao/ocorrencias?${query}`); tbody.replaceChildren();
    availableReasons=[...new Set(data.ocorrencias.map(item=>item.motivo).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"pt-BR"));
    if(!document.getElementById("reason-options").hidden) updateReasonOptions();
    populateFilter("unit",data.ocorrencias.map(item=>item.unidade));
    populateFilter("team",data.ocorrencias.map(item=>item.equipe));
    populateFilter("reviewer",data.ocorrencias.map(item=>item.analisador));
    const base=data.ocorrencias.filter(item=>
      (!appliedExtra.unit||item.unidade===appliedExtra.unit) &&
      (!appliedExtra.team||item.equipe===appliedExtra.team) &&
      (!appliedExtra.reviewer||(appliedExtra.reviewer==="__none"?!item.analisador:item.analisador===appliedExtra.reviewer)) &&
      (!appliedExtra.reason||normalizeText(item.motivo).includes(normalizeText(appliedExtra.reason)))
    );
    const statusSelect=document.getElementById("status");
    [...statusSelect.options].forEach(option=>{
      const count=option.value ? base.filter(item=>item.status===option.value).length : base.length;
      option.textContent=`${option.dataset.label || (option.dataset.label=option.textContent)} (${count})`;
    });
    syncSelect(statusSelect);
    const rows=base.filter(item=>!appliedParams.get("status")||item.status===appliedParams.get("status"));
    updateSummary(rows);renderRail(rows);document.getElementById("result-count").textContent=rows.length;
    document.getElementById("table-count").textContent=`${rows.length} ${rows.length===1?"encontrada":"encontradas"}`;
    if(!rows.length){tbody.innerHTML='<tr><td colspan="6" class="empty">Nenhuma solicitação encontrada para os filtros selecionados.</td></tr>';return;}
    rows.forEach(item=>{const tr=document.createElement("tr");
      const employee=document.createElement("td");employee.className="employee-cell";employee.innerHTML=`<strong>${value(item.funcionario)}</strong><span>${value(item.matricula)}</span>`;tr.appendChild(employee);
      const category=document.createElement("td");category.className="category-cell";category.textContent=labels[item.tipo]||item.tipo;tr.appendChild(category);
      const created=document.createElement("td");created.textContent=localDate(item.criada_em);
      if(["pendente_gestor","encaminhada_rh"].includes(item.status)&&item.criada_em){
        const days=Math.max(0,Math.floor((Date.now()-new Date(item.criada_em).getTime())/86400000));
        const elapsed=document.createElement("small");elapsed.className="waiting-age";elapsed.textContent=days===0?"Aberta hoje":`Aguardando há ${days} ${days===1?"dia":"dias"}`;created.appendChild(elapsed);
      }
      const status=document.createElement("td");const pill=document.createElement("span");pill.className=`status-pill status-${item.status}`;pill.textContent=statusLabels[item.status]||item.status;status.appendChild(pill);tr.appendChild(status);
      tr.appendChild(created);
      const attachment=document.createElement("td");attachment.textContent=item.comprovante ? item.comprovante.estado : "Sem comprovante";tr.appendChild(attachment);
      const td=document.createElement("td"),button=document.createElement("button");td.className="action-col-cell";button.className="btn-table-action";button.textContent=(item.acoes_permitidas||[]).length?"Analisar":"Consultar";button.onclick=()=>openDetail(item.id);td.appendChild(button);tr.appendChild(td);tbody.appendChild(tr);});
  }catch(error){tbody.innerHTML=`<tr><td colspan="6" class="empty"></td></tr>`;tbody.querySelector("td").textContent=error.message;document.getElementById("oldest-requests").textContent="Não foi possível carregar as solicitações.";document.getElementById("request-categories").textContent="Não foi possível carregar as categorias.";}
}
function updateSummary(rows){const pending=rows.filter(item=>["pendente_gestor","solicitada","em_analise_gestor"].includes(item.status)).length,review=rows.filter(item=>["encaminhada_rh","em_analise_rh"].includes(item.status)).length,done=rows.filter(item=>["aprovada","rejeitada","cancelada"].includes(item.status)).length;document.getElementById("summary-pending").textContent=pending;document.getElementById("summary-review").textContent=review;document.getElementById("summary-done").textContent=done;}
async function openDetail(id){
  try{const item=await api(`/api/gestao/ocorrencias/${encodeURIComponent(id)}`);selectedId=id;
    const fields=[["Funcionário",`${value(item.funcionario)} (${value(item.matricula)})`],["Categoria",labels[item.tipo]||item.tipo],["Status",statusLabels[item.status]||item.status],["Motivo",item.motivo],["Horário original",localDate(item.instante_original)],["Horário solicitado",localDate(item.instante_solicitado)],["Tipo original",value(item.tipo_marcacao_original)],["Tipo solicitado",value(item.tipo_marcacao_solicitado)],["Solicitante",value(item.solicitante)],["Último responsável",value(item.analisador)],["Última observação",value(item.observacao)]];
    const dl=document.getElementById("detail-content");dl.replaceChildren();fields.forEach(([label,text])=>{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=text;dl.append(dt,dd);});
    const attachment=document.getElementById("attachment-detail");attachment.replaceChildren();if(item.comprovante){const meta=document.createElement("span");meta.textContent=`${item.comprovante.nome} · ${item.comprovante.tipo_mime} · ${(item.comprovante.tamanho_bytes/1024).toFixed(1)} KiB · ${item.comprovante.estado}`;attachment.appendChild(meta);if(item.comprovante.situacao==="disponivel"){const download=document.createElement("a");download.className="btn-secondary";download.textContent="Baixar comprovante";download.href=`/api/gestao/ocorrencias/${encodeURIComponent(id)}/comprovante/download`;attachment.appendChild(download);}}else{attachment.textContent="Nenhum comprovante enviado.";}document.getElementById("retry-scan").hidden=!item.comprovante||item.comprovante.situacao!=="falha_temporaria";
    const actions=new Set(item.acoes_permitidas||[]);document.getElementById("approve").hidden=!actions.has("aprovar");document.getElementById("reject").hidden=!actions.has("rejeitar");document.getElementById("forward").hidden=!actions.has("encaminhar-rh");document.getElementById("observation").disabled=actions.size===0;document.getElementById("observation").value="";document.getElementById("decision-error").textContent="";
    const timeline=document.getElementById("timeline");timeline.replaceChildren();(item.historico||[]).forEach(event=>{const li=document.createElement("li"),title=document.createElement("strong"),meta=document.createElement("span");title.textContent=`${statusLabels[event.estado_novo]||event.estado_novo||event.acao}${event.observacao?` — ${event.observacao}`:""}`;meta.className="meta";meta.textContent=`${localDate(event.ocorrida_em)} · ${value(event.responsavel)}${event.papel?` (${event.papel})`:""}`;li.append(title,meta);timeline.appendChild(li);});if(!timeline.children.length){const li=document.createElement("li");li.textContent="Histórico indisponível.";timeline.appendChild(li);}document.getElementById("detail").showModal();
  }catch(error){alert(error.message);}
}
async function decide(action){
  const error=document.getElementById("decision-error");error.textContent="";
  try{await api(`/api/gestao/ocorrencias/${encodeURIComponent(selectedId)}/${action}`,{method:"POST",body:JSON.stringify({observacao:document.getElementById("observation").value.trim()})});document.getElementById("detail").close();await load();}catch(reason){if(reason.status===409){await load();await openDetail(selectedId);document.getElementById("decision-error").textContent=`Conflito: ${reason.message} Os dados foram atualizados.`;}else{error.textContent=reason.message;}}
}
async function retryScan(){const error=document.getElementById("decision-error");error.textContent="";try{await api(`/api/gestao/ocorrencias/${encodeURIComponent(selectedId)}/comprovante/retry-scan`,{method:"POST"});await openDetail(selectedId);}catch(reason){error.textContent=reason.message;}}
document.addEventListener("DOMContentLoaded",async()=>{document.getElementById("search").onclick=()=>{appliedParams=params();appliedExtra={unit:document.getElementById("unit").value,team:document.getElementById("team").value,reviewer:document.getElementById("reviewer").value,reason:document.getElementById("reason-filter").value};load();};document.getElementById("clear-filters").onclick=()=>{document.querySelectorAll(".filter-card select").forEach(select=>{select.value="";updateSelect(select);});document.querySelectorAll("#start,#end").forEach(input=>{if(input._flatpickr)input._flatpickr.clear();else input.value="";});document.getElementById("reason-filter").value="";appliedParams=new URLSearchParams();appliedExtra={};load();};document.getElementById("refresh").onclick=load;document.getElementById("approve").onclick=()=>decide("aprovar");document.getElementById("reject").onclick=()=>decide("rejeitar");document.getElementById("forward").onclick=()=>decide("encaminhar-rh");document.getElementById("retry-scan").onclick=retryScan;document.getElementById("toggle-filters").onclick=event=>{const panel=document.getElementById("advanced-filters");panel.hidden=!panel.hidden;event.currentTarget.setAttribute("aria-expanded",String(!panel.hidden));event.currentTarget.textContent=panel.hidden?"Mais filtros +":"Menos filtros −";};initializeDateRange();activateSelects();setupReasonFilter();appliedParams=params();try{await loadEmployees();await load();}catch(error){document.getElementById("rows").innerHTML='<tr><td colspan="6" class="empty"></td></tr>';document.querySelector("#rows td").textContent=error.message;}});
