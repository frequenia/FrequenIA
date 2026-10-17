const markingLabels={entrada:"Entrada",saida_intervalo:"Saída para intervalo",retorno_intervalo:"Retorno do intervalo",saida:"Saída"};
const requestLabels={esquecimento_marcacao:"Esquecimento de marcação",horario_incorreto:"Horário incorreto",tipo_incorreto:"Tipo incorreto",justificativa:"Justificativa"};
const statusLabels={pendente_gestor:"Pendente com gestor",encaminhada_rh:"Encaminhada ao RH",aprovada:"Aprovada",rejeitada:"Rejeitada",cancelada:"Cancelada"};
let markings=[];

async function api(url,options={}){
  const headers={...(options.headers||{})};if(!(options.body instanceof FormData))headers["Content-Type"]="application/json";
  const response=await fetch(url,{credentials:"same-origin",...options,headers});
  let data={};try{data=await response.json();}catch(_error){}
  if(response.status===401){window.top.location.href="/login-page";throw new Error("Sua sessão expirou.");}
  if(!response.ok)throw new Error(data.erro||"Não foi possível concluir a operação.");
  return data;
}
function localDate(value){return value?new Intl.DateTimeFormat("pt-BR",{dateStyle:"short",timeStyle:"short",timeZone:"America/Sao_Paulo"}).format(new Date(value)):"Não informado";}
function empty(container,message){container.innerHTML="";const node=document.createElement("div");node.className="empty-state";node.textContent=message;container.appendChild(node);}
function periodLabel(item){const start=String(item.inicio||"").slice(0,5),end=String(item.fim||"").slice(0,5);return `${start} às ${end}${item.fim_dia_offset?" (dia seguinte)":""}`;}
function attachmentControls(item){const box=document.createElement("div"),attachment=item.comprovante;box.className="attachment-controls";const label=document.createElement("small");label.textContent=attachment?`${attachment.nome} · ${attachment.tipo_mime} · ${(attachment.tamanho_bytes/1024).toFixed(1)} KiB · ${attachment.estado}`:"Sem comprovante";box.appendChild(label);if(attachment?.situacao==="disponivel"){const download=document.createElement("a");download.className="btn-secondary";download.textContent="Baixar comprovante";download.href=`/api/ocorrencias/${encodeURIComponent(item.id)}/comprovante/download`;box.appendChild(download);}if(item.status==="pendente_gestor"){const input=document.createElement("input");input.type="file";input.accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png";input.hidden=true;input.onchange=async()=>{if(!input.files.length)return;try{await uploadAttachment(item.id,input.files[0]);await loadRequests();}catch(error){alert(error.message);}};const choose=document.createElement("button");choose.type="button";choose.className="btn-secondary";choose.textContent=attachment?"Substituir":"Adicionar comprovante";choose.onclick=()=>input.click();box.append(input,choose);if(attachment){const remove=document.createElement("button");remove.type="button";remove.className="btn-secondary";remove.textContent="Remover comprovante";remove.onclick=()=>removeAttachment(item.id);box.appendChild(remove);}}return box;}
async function uploadAttachment(id,file){if(file.size>10*1024*1024)throw new Error("O comprovante deve ter no máximo 10 MiB.");const body=new FormData();body.append("comprovante",file);return api(`/api/ocorrencias/${encodeURIComponent(id)}/comprovante`,{method:"PUT",body});}
async function removeAttachment(id){if(!confirm("Deseja remover este comprovante?"))return;try{await api(`/api/ocorrencias/${encodeURIComponent(id)}/comprovante`,{method:"DELETE"});await loadRequests();}catch(error){alert(error.message);}}

async function loadMarks(){
  const container=document.getElementById("marksList");empty(container,"Carregando marcações...");
  try{
    const data=await api("/api/marcacoes");markings=data.marcacoes||[];container.replaceChildren();
    const original=document.getElementById("originalMark");original.replaceChildren(new Option("Selecione uma marcação",""));
    markings.forEach(item=>original.add(new Option(`${markingLabels[item.tipo]||item.tipo} — ${localDate(item.instante)}`,item.id)));
    if(!markings.length){empty(container,"Nenhuma marcação encontrada.");document.getElementById("lastMark").textContent="Nenhuma";document.getElementById("lastMarkType").textContent="";return;}
    const latest=markings[0];document.getElementById("lastMark").textContent=localDate(latest.instante);document.getElementById("lastMarkType").textContent=markingLabels[latest.tipo]||latest.tipo;
    markings.forEach(item=>{const row=document.createElement("article");row.className="list-item";const main=document.createElement("div"),title=document.createElement("strong"),date=document.createElement("small"),origin=document.createElement("div"),originTitle=document.createElement("span"),originValue=document.createElement("small"),status=document.createElement("span");title.textContent=markingLabels[item.tipo]||item.tipo;date.textContent=localDate(item.instante);main.append(title,date);originTitle.textContent="Origem";originValue.textContent=item.origem||"Não informada";origin.append(originTitle,originValue);status.className="status-pill";status.textContent=item.estado||"confirmada";row.append(main,origin,status);container.appendChild(row);});
  }catch(error){empty(container,error.message);}
}

async function loadSchedule(date){
  const detail=document.getElementById("scheduleDetail");empty(detail,"Carregando jornada...");
  try{
    const data=await api(`/api/jornada?data=${encodeURIComponent(date)}`),journey=data.jornada;detail.replaceChildren();
    if(!journey){empty(detail,"Não há jornada atribuída para esta data.");return null;}
    const name=document.createElement("div");name.className="schedule-name";name.textContent=journey.folga?"Folga programada":(journey.turno?.nome||"Sem jornada");
    const periods=document.createElement("div");periods.className="periods";
    const weekday=new Date(`${date}T12:00:00`).getDay();const todayPeriods=(journey.periodos||[]).filter(item=>Number(item.dia_semana)===weekday);
    if(todayPeriods.length)todayPeriods.forEach(item=>{const node=document.createElement("span");node.className="period";node.textContent=periodLabel(item);periods.appendChild(node);});else periods.textContent="Sem período de trabalho nesta data.";
    detail.append(name,periods);return {journey,todayPeriods};
  }catch(error){empty(detail,error.message);return null;}
}

async function loadRequests(){
  const container=document.getElementById("requestsList");empty(container,"Carregando solicitações...");
  try{
    const data=await api("/api/ocorrencias"),rows=data.ocorrencias||[];container.replaceChildren();
    document.getElementById("pendingCount").textContent=rows.filter(item=>["pendente_gestor","encaminhada_rh"].includes(item.status)).length;
    if(!rows.length){empty(container,"Você ainda não possui solicitações.");return;}
    rows.forEach(item=>{const row=document.createElement("article");row.className="list-item";
      const main=document.createElement("div"),title=document.createElement("strong"),reason=document.createElement("small");title.textContent=requestLabels[item.tipo]||item.tipo;reason.textContent=item.motivo||"Sem motivo informado";main.append(title,reason,attachmentControls(item));
      const dates=document.createElement("div"),created=document.createElement("span"),observation=document.createElement("small");created.textContent=localDate(item.criada_em);observation.textContent=item.observacao||"Aguardando análise";dates.append(created,observation);
      const actions=document.createElement("div");const status=document.createElement("span");status.className=`status-pill ${item.status}`;status.textContent=statusLabels[item.status]||item.status;actions.appendChild(status);
      if((item.acoes_permitidas||[]).includes("cancelar")){const button=document.createElement("button");button.type="button";button.className="btn-secondary";button.textContent="Cancelar";button.style.marginLeft="8px";button.onclick=()=>cancelRequest(item.id);actions.appendChild(button);}
      row.append(main,dates,actions);container.appendChild(row);
    });
  }catch(error){empty(container,error.message);document.getElementById("pendingCount").textContent="—";}
}

function syncRequestFields(){
  const type=document.getElementById("requestType").value;
  const original=["horario_incorreto","tipo_incorreto"].includes(type),instant=["esquecimento_marcacao","horario_incorreto"].includes(type),markType=["esquecimento_marcacao","tipo_incorreto"].includes(type);
  document.getElementById("originalMarkField").hidden=!original;document.getElementById("originalMark").required=original;
  document.getElementById("requestedInstantField").hidden=!instant;document.getElementById("requestedInstant").required=instant;
  document.getElementById("requestedMarkTypeField").hidden=!markType;
}
function openRequest(){const input=document.getElementById("requestedInstant"),now=new Date();now.setMinutes(now.getMinutes()-now.getTimezoneOffset());input.value=now.toISOString().slice(0,16);document.getElementById("requestError").textContent="";syncRequestFields();document.getElementById("requestDialog").showModal();}
async function submitRequest(event){
  event.preventDefault();const type=document.getElementById("requestType").value,body={tipo:type,motivo:document.getElementById("requestReason").value.trim()};
  if(["horario_incorreto","tipo_incorreto"].includes(type))body.marcacao_id=document.getElementById("originalMark").value;
  if(["esquecimento_marcacao","horario_incorreto"].includes(type))body.instante_solicitado=new Date(document.getElementById("requestedInstant").value).toISOString();
  if(["esquecimento_marcacao","tipo_incorreto"].includes(type))body.tipo_marcacao_solicitado=document.getElementById("requestedMarkType").value;
  const button=document.getElementById("submitRequest");button.disabled=true;document.getElementById("requestError").textContent="";
  const selected=document.getElementById("requestAttachment").files[0];let requestBody=JSON.stringify(body);if(selected){if(selected.size>10*1024*1024){document.getElementById("requestError").textContent="O comprovante deve ter no máximo 10 MiB.";button.disabled=false;return;}requestBody=new FormData();Object.entries(body).forEach(([key,value])=>requestBody.append(key,value));requestBody.append("comprovante",selected);}
  try{await api("/api/ocorrencias",{method:"POST",body:requestBody});document.getElementById("requestDialog").close();document.getElementById("requestForm").reset();await loadRequests();}
  catch(error){document.getElementById("requestError").textContent=error.message;}finally{button.disabled=false;}
}
async function cancelRequest(id){if(!confirm("Deseja cancelar esta solicitação?"))return;try{await api(`/api/ocorrencias/${encodeURIComponent(id)}/cancelar`,{method:"POST",body:"{}"});await loadRequests();}catch(error){alert(error.message);}}
function selectPanel(id){document.querySelectorAll(".tab").forEach(tab=>tab.classList.toggle("active",tab.dataset.panel===id));document.querySelectorAll(".panel").forEach(panel=>{const selected=panel.id===id;panel.classList.toggle("active",selected);panel.hidden=!selected;});}

document.addEventListener("DOMContentLoaded",async()=>{
  const today=new Date();today.setMinutes(today.getMinutes()-today.getTimezoneOffset());const date=today.toISOString().slice(0,10);document.getElementById("scheduleDate").value=date;
  document.querySelectorAll(".tab").forEach(tab=>tab.onclick=()=>selectPanel(tab.dataset.panel));document.getElementById("refreshMarks").onclick=loadMarks;document.getElementById("searchSchedule").onclick=()=>loadSchedule(document.getElementById("scheduleDate").value);document.getElementById("openRequest").onclick=openRequest;document.getElementById("closeRequest").onclick=()=>document.getElementById("requestDialog").close();document.getElementById("cancelRequest").onclick=()=>document.getElementById("requestDialog").close();document.getElementById("requestType").onchange=syncRequestFields;document.getElementById("requestForm").onsubmit=submitRequest;
  if(location.hash==="#solicitacoes")selectPanel("requestsPanel");
  const [,schedule]=await Promise.all([loadMarks(),loadSchedule(date),loadRequests()]);
  if(schedule){document.getElementById("scheduleName").textContent=schedule.journey.folga?"Folga programada":(schedule.journey.turno?.nome||"Não atribuída");document.getElementById("schedulePeriods").textContent=schedule.todayPeriods.length?schedule.todayPeriods.map(periodLabel).join(" · "):"Sem período hoje";}else{document.getElementById("scheduleName").textContent="Não atribuída";document.getElementById("schedulePeriods").textContent="";}
});
