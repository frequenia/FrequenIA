let selectedId = null;
const labels = {esquecimento_marcacao:"Esquecimento de marcação",horario_incorreto:"Horário incorreto",tipo_incorreto:"Tipo incorreto",justificativa:"Justificativa",outro:"Outro"};
const statusLabels = {pendente_gestor:"Pendente com gestor",solicitada:"Pendente com gestor",em_analise_gestor:"Pendente com gestor",encaminhada_rh:"Encaminhada ao RH",aprovada:"Aprovada",rejeitada:"Rejeitada",cancelada:"Cancelada"};

class ApiError extends Error { constructor(message,status){super(message);this.status=status;} }

async function api(url, options={}) {
  const response = await fetch(url, {credentials:"same-origin", ...options, headers:{"Content-Type":"application/json", ...(options.headers||{})}});
  let data={}; try{data=await response.json();}catch(_error){}
  if(!response.ok) throw new ApiError(data.erro || "Não foi possível concluir a operação.",response.status);
  return data;
}
function value(value){return value || "Não informado";}
function localDate(value){return value ? new Intl.DateTimeFormat("pt-BR",{dateStyle:"short",timeStyle:"short",timeZone:"America/Sao_Paulo"}).format(new Date(value)) : "Não informado";}

function syncSelect(select){const wrapper=select.closest(".custom-select");if(!wrapper)return;const menu=wrapper.querySelector(".select-menu"),trigger=wrapper.querySelector(".select-trigger");menu.replaceChildren();Array.from(select.options).forEach(option=>{const item=document.createElement("button");item.type="button";item.className="select-option";item.dataset.value=option.value;item.textContent=option.textContent;item.onclick=()=>{select.value=option.value;select.dispatchEvent(new Event("change",{bubbles:true}));updateSelect(select);wrapper.classList.remove("open");};menu.appendChild(item);});updateSelect(select);if(trigger)trigger.disabled=!select.options.length;}
function updateSelect(select){const wrapper=select.closest(".custom-select");if(!wrapper)return;const selected=select.options[select.selectedIndex],trigger=wrapper.querySelector(".select-trigger");if(selected)trigger.querySelector(".select-label").textContent=selected.textContent;wrapper.querySelectorAll(".select-option").forEach(item=>item.classList.toggle("selected",item.dataset.value===select.value));}
function customSelect(select){if(select.closest(".custom-select"))return;const wrapper=document.createElement("div");wrapper.className="custom-select";select.parentNode.insertBefore(wrapper,select);wrapper.appendChild(select);select.classList.add("native-select");const trigger=document.createElement("button");trigger.type="button";trigger.className="select-trigger";trigger.setAttribute("aria-haspopup","listbox");trigger.innerHTML='<span class="select-label"></span><span class="select-chevron" aria-hidden="true"></span>';const menu=document.createElement("div");menu.className="select-menu";menu.setAttribute("role","listbox");wrapper.insertBefore(trigger,select);wrapper.appendChild(menu);trigger.onclick=()=>{document.querySelectorAll(".custom-select.open").forEach(item=>{if(item!==wrapper)item.classList.remove("open")});wrapper.classList.toggle("open")};select.onchange=()=>updateSelect(select);syncSelect(select);}
function activateSelects(){document.querySelectorAll("select").forEach(customSelect);if(!document.body.dataset.selectListener){document.body.dataset.selectListener="1";document.addEventListener("click",event=>{if(!event.target.closest(".custom-select"))document.querySelectorAll(".custom-select.open").forEach(item=>item.classList.remove("open"));});}}

async function loadEmployees(){
  const rows=await api("/api/gestao/funcionarios"); const select=document.getElementById("employee");
  rows.forEach(item=>select.add(new Option(`${item.nome} - ${item.matricula}`,item.funcionario_id))); syncSelect(select);
}
function params(){
  const result=new URLSearchParams();
  [["funcionario_id","employee"],["status","status"],["tipo","type"],["inicio","start"],["fim","end"]].forEach(([key,id])=>{const v=document.getElementById(id).value;if(v)result.set(key,v);});
  return result;
}
async function load(){
  const tbody=document.getElementById("rows"); tbody.innerHTML='<tr><td colspan="5" class="empty">Carregando...</td></tr>';
  try{
    const data=await api(`/api/gestao/ocorrencias?${params()}`); tbody.replaceChildren();
    updateSummary(data.ocorrencias);document.getElementById("result-count").textContent=data.ocorrencias.length;
    if(!data.ocorrencias.length){tbody.innerHTML='<tr><td colspan="5" class="empty">Nenhuma solicitação encontrada para os filtros selecionados.</td></tr>';return;}
    data.ocorrencias.forEach(item=>{const tr=document.createElement("tr");
      const employee=document.createElement("td");employee.className="employee-cell";employee.innerHTML=`<strong>${value(item.funcionario)}</strong><span>${value(item.matricula)}</span>`;tr.appendChild(employee);
      const category=document.createElement("td");category.className="category-cell";category.textContent=labels[item.tipo]||item.tipo;tr.appendChild(category);
      const created=document.createElement("td");created.textContent=localDate(item.criada_em);tr.appendChild(created);
      const status=document.createElement("td");const pill=document.createElement("span");pill.className=`status-pill status-${item.status}`;pill.textContent=statusLabels[item.status]||item.status;status.appendChild(pill);tr.appendChild(status);
      const td=document.createElement("td"),button=document.createElement("button");button.className="btn-primary";button.textContent="Detalhar";button.onclick=()=>openDetail(item.id);td.appendChild(button);tr.appendChild(td);tbody.appendChild(tr);});
  }catch(error){tbody.innerHTML=`<tr><td colspan="5" class="empty"></td></tr>`;tbody.querySelector("td").textContent=error.message;}
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
document.addEventListener("DOMContentLoaded",async()=>{document.getElementById("search").onclick=load;document.getElementById("refresh").onclick=load;document.getElementById("approve").onclick=()=>decide("aprovar");document.getElementById("reject").onclick=()=>decide("rejeitar");document.getElementById("forward").onclick=()=>decide("encaminhar-rh");document.getElementById("retry-scan").onclick=retryScan;activateSelects();try{await loadEmployees();await load();}catch(error){document.getElementById("rows").innerHTML='<tr><td colspan="5" class="empty"></td></tr>';document.querySelector("#rows td").textContent=error.message;}});
