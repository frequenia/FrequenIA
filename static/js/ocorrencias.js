let selectedId = null;
const labels = {esquecimento_marcacao:"Esquecimento de marcação",horario_incorreto:"Horário incorreto",tipo_incorreto:"Tipo incorreto",justificativa:"Justificativa",outro:"Outro"};
const statusLabels = {pendente_gestor:"Pendente com gestor",encaminhada_rh:"Encaminhada ao RH",aprovada:"Aprovada",rejeitada:"Rejeitada",cancelada:"Cancelada"};

class ApiError extends Error { constructor(message,status){super(message);this.status=status;} }

async function api(url, options={}) {
  const response = await fetch(url, {credentials:"same-origin", ...options, headers:{"Content-Type":"application/json", ...(options.headers||{})}});
  let data={}; try{data=await response.json();}catch(_error){}
  if(!response.ok) throw new ApiError(data.erro || "Não foi possível concluir a operação.",response.status);
  return data;
}
function value(value){return value || "Não informado";}
function localDate(value){return value ? new Intl.DateTimeFormat("pt-BR",{dateStyle:"short",timeStyle:"short",timeZone:"America/Sao_Paulo"}).format(new Date(value)) : "Não informado";}

async function loadEmployees(){
  const rows=await api("/api/gestao/funcionarios"); const select=document.getElementById("employee");
  rows.forEach(item=>select.add(new Option(`${item.nome} - ${item.matricula}`,item.funcionario_id)));
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
    if(!data.ocorrencias.length){tbody.innerHTML='<tr><td colspan="5" class="empty">Nenhuma solicitação encontrada.</td></tr>';return;}
    data.ocorrencias.forEach(item=>{const tr=document.createElement("tr");
      [value(item.funcionario),labels[item.tipo]||item.tipo,localDate(item.criada_em),statusLabels[item.status]||item.status].forEach((text,index)=>{const td=document.createElement("td");td.textContent=text;if(index===3)td.className="status";tr.appendChild(td);});
      const td=document.createElement("td"),button=document.createElement("button");button.className="btn-primary";button.textContent="Detalhar";button.onclick=()=>openDetail(item.id);td.appendChild(button);tr.appendChild(td);tbody.appendChild(tr);});
  }catch(error){tbody.innerHTML=`<tr><td colspan="5" class="empty"></td></tr>`;tbody.querySelector("td").textContent=error.message;}
}
async function openDetail(id){
  try{const item=await api(`/api/gestao/ocorrencias/${encodeURIComponent(id)}`);selectedId=id;
    const fields=[["Funcionário",`${value(item.funcionario)} (${value(item.matricula)})`],["Categoria",labels[item.tipo]||item.tipo],["Status",statusLabels[item.status]||item.status],["Motivo",item.motivo],["Horário original",localDate(item.instante_original)],["Horário solicitado",localDate(item.instante_solicitado)],["Tipo original",value(item.tipo_marcacao_original)],["Tipo solicitado",value(item.tipo_marcacao_solicitado)],["Solicitante",value(item.solicitante)],["Último responsável",value(item.analisador)],["Última observação",value(item.observacao)]];
    const dl=document.getElementById("detail-content");dl.replaceChildren();fields.forEach(([label,text])=>{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=text;dl.append(dt,dd);});
    const actions=new Set(item.acoes_permitidas||[]);document.getElementById("approve").hidden=!actions.has("aprovar");document.getElementById("reject").hidden=!actions.has("rejeitar");document.getElementById("forward").hidden=!actions.has("encaminhar-rh");document.getElementById("observation").disabled=actions.size===0;document.getElementById("observation").value="";document.getElementById("decision-error").textContent="";
    const timeline=document.getElementById("timeline");timeline.replaceChildren();(item.historico||[]).forEach(event=>{const li=document.createElement("li"),title=document.createElement("strong"),meta=document.createElement("span");title.textContent=`${statusLabels[event.estado_novo]||event.estado_novo||event.acao}${event.observacao?` — ${event.observacao}`:""}`;meta.className="meta";meta.textContent=`${localDate(event.ocorrida_em)} · ${value(event.responsavel)}${event.papel?` (${event.papel})`:""}`;li.append(title,meta);timeline.appendChild(li);});if(!timeline.children.length){const li=document.createElement("li");li.textContent="Histórico indisponível.";timeline.appendChild(li);}document.getElementById("detail").showModal();
  }catch(error){alert(error.message);}
}
async function decide(action){
  const error=document.getElementById("decision-error");error.textContent="";
  try{await api(`/api/gestao/ocorrencias/${encodeURIComponent(selectedId)}/${action}`,{method:"POST",body:JSON.stringify({observacao:document.getElementById("observation").value.trim()})});document.getElementById("detail").close();await load();}catch(reason){if(reason.status===409){await load();await openDetail(selectedId);document.getElementById("decision-error").textContent=`Conflito: ${reason.message} Os dados foram atualizados.`;}else{error.textContent=reason.message;}}
}
document.addEventListener("DOMContentLoaded",async()=>{document.getElementById("search").onclick=load;document.getElementById("approve").onclick=()=>decide("aprovar");document.getElementById("reject").onclick=()=>decide("rejeitar");document.getElementById("forward").onclick=()=>decide("encaminhar-rh");try{await loadEmployees();await load();}catch(error){document.getElementById("rows").innerHTML='<tr><td colspan="5" class="empty"></td></tr>';document.querySelector("#rows td").textContent=error.message;}});
