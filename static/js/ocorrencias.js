let selectedId = null;
const labels = {esquecimento_marcacao:"Esquecimento de marcação",horario_incorreto:"Horário incorreto",tipo_incorreto:"Tipo incorreto",justificativa:"Justificativa",outro:"Outro"};

async function api(url, options={}) {
  const response = await fetch(url, {credentials:"same-origin", ...options, headers:{"Content-Type":"application/json", ...(options.headers||{})}});
  let data={}; try{data=await response.json();}catch(_error){}
  if(!response.ok) throw new Error(data.erro || "Não foi possível concluir a operação.");
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
      [value(item.funcionario),labels[item.tipo]||item.tipo,localDate(item.criada_em),item.status].forEach((text,index)=>{const td=document.createElement("td");td.textContent=text;if(index===3)td.className="status";tr.appendChild(td);});
      const td=document.createElement("td"),button=document.createElement("button");button.className="btn-primary";button.textContent="Detalhar";button.onclick=()=>openDetail(item.id);td.appendChild(button);tr.appendChild(td);tbody.appendChild(tr);});
  }catch(error){tbody.innerHTML=`<tr><td colspan="5" class="empty"></td></tr>`;tbody.querySelector("td").textContent=error.message;}
}
async function openDetail(id){
  try{const item=await api(`/api/gestao/ocorrencias/${encodeURIComponent(id)}`);selectedId=id;
    const fields=[["Funcionário",`${value(item.funcionario)} (${value(item.matricula)})`],["Categoria",labels[item.tipo]||item.tipo],["Status",item.status],["Motivo",item.motivo],["Horário original",localDate(item.instante_original)],["Horário solicitado",localDate(item.instante_solicitado)],["Tipo original",value(item.tipo_marcacao_original)],["Tipo solicitado",value(item.tipo_marcacao_solicitado)],["Solicitante",value(item.solicitante)],["Analisador",value(item.analisador)],["Observação",value(item.observacao)]];
    const dl=document.getElementById("detail-content");dl.replaceChildren();fields.forEach(([label,text])=>{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=text;dl.append(dt,dd);});
    const pending=item.status==="pendente";document.getElementById("approve").hidden=!pending;document.getElementById("reject").hidden=!pending;document.getElementById("observation").disabled=!pending;document.getElementById("observation").value="";document.getElementById("decision-error").textContent="";document.getElementById("detail").showModal();
  }catch(error){alert(error.message);}
}
async function decide(action){
  const error=document.getElementById("decision-error");error.textContent="";
  try{await api(`/api/gestao/ocorrencias/${encodeURIComponent(selectedId)}/${action}`,{method:"POST",body:JSON.stringify({observacao:document.getElementById("observation").value.trim()})});document.getElementById("detail").close();await load();}catch(reason){error.textContent=reason.message;}
}
document.addEventListener("DOMContentLoaded",async()=>{document.getElementById("search").onclick=load;document.getElementById("approve").onclick=()=>decide("aprovar");document.getElementById("reject").onclick=()=>decide("rejeitar");try{await loadEmployees();await load();}catch(error){document.getElementById("rows").innerHTML='<tr><td colspan="5" class="empty"></td></tr>';document.querySelector("#rows td").textContent=error.message;}});
