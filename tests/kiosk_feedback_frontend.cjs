const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.textContent=''; this.value=''; this.hidden=false; this.open=false; this.dataset={}; this.disabled=false; this.events={}; this.classList={add(){},remove(){}}; }
  addEventListener(name,fn) { (this.events[name]??=[]).push(fn); }
  focus() {}
  showModal() { this.open=true; }
  close() { this.open=false; for(const fn of this.events.close||[]) fn(); }
}
const elements=new Map();
const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const timers=new Map();let timerId=0;let requests=[];let responseBody;
const stream={getTracks:()=>[{stop(){}}]};
const windowEvents={};
const context=vm.createContext({
  document:{getElementById:get,createElement:()=>({getContext:()=>({drawImage(){}}),toBlob:fn=>fn({type:'image/jpeg'})})},
  window:{isSecureContext:true,crypto:{randomUUID:()=> 'synthetic-key'},addEventListener:(name,fn)=>(windowEvents[name]??=[]).push(fn)},
  navigator:{mediaDevices:{getUserMedia:async()=>stream}},
  HTMLMediaElement:{HAVE_CURRENT_DATA:2},DOMException,Intl,Date,Number,Uint8Array,
  setTimeout:(fn,ms)=>{const id=++timerId;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),
  FormData:class {append(){}},
  fetch:async(url,options)=>{requests.push({url,options});return {ok:true,status:201,json:async()=>responseBody};},
  testStream:stream,
});
get('video').play=async()=>{};
get('video').readyState=2;get('video').videoWidth=1280;get('video').videoHeight=720;
const source=fs.readFileSync('static/js/reconhecimento.js','utf8').replace(/\nopenCamera\(\);\s*$/,'');
vm.runInContext(source,context);
const run=code=>vm.runInContext(code,context);

(async()=>{
  const body={funcionario:{nome:'Funcionario de demonstracao'},marcacao:{estado:'confirmada',tipo:'saida_intervalo',instante:'2026-11-22T15:34:56+00:00'},jornada:{timezone:'America/Sao_Paulo'}};
  context.fixture=body;
  const receipt=run('markingConfirmation(fixture)');
  assert.equal(receipt.name,body.funcionario.nome);
  assert.equal(receipt.type,'Saída para intervalo');
  assert.match(receipt.time,/12:34:56/);
  for(const invalid of [null,{}, {...body,marcacao:{...body.marcacao,estado:'cancelada'}},{...body,marcacao:{...body.marcacao,instante:'15:34'}}]) {
    context.fixture=invalid;assert.equal(run('markingConfirmation(fixture)'),null);
  }
  context.fixture=body;responseBody=body;
  await run('openCamera()'); get('matricula').value='DEMO';
  await run('registerClock()');
  assert.equal(requests.length,1);
  assert.equal(requests[0].url,'/api/quiosque/marcacoes/facial');
  assert.equal(get('kiosk-feedback').open,true);
  assert.equal(get('feedback-receipt').hidden,false);
  assert.equal(get('receipt-name').textContent,body.funcionario.nome);
  assert.equal(get('receipt-type').textContent,'Saída para intervalo');
  assert.equal(get('matricula').value,'');
  const expiry=[...timers.values()].find(x=>x.ms===10000);assert.ok(expiry);
  expiry.fn();
  assert.equal(get('receipt-name').textContent,'');assert.equal(get('feedback-receipt').hidden,true);
  await Promise.resolve();await Promise.resolve();
  run("showFeedback(errorFeedback({codigo:'jornada_nao_configurada'},409))");
  assert.equal(get('feedback-title').textContent,'Jornada não configurada');
  assert.equal(get('receipt-name').textContent,'');assert.equal(get('feedback-receipt').hidden,true);
  assert.equal(timers.size,0,'erro precisa permanecer para leitura');
  run('showFeedback(errorFeedback({},0))');
  assert.match(get('feedback-hint').textContent,/histórico/);
  context.fixture={...body,funcionario:{nome:'<img src=x onerror=alert(1)>'}};
  run("showFeedback({title:'Confirmado',message:'OK',hint:'',confirmation:markingConfirmation(fixture)})");
  assert.equal(get('receipt-name').textContent,'<img src=x onerror=alert(1)>');
  for(const fn of windowEvents.pagehide)fn();
  assert.equal(get('receipt-name').textContent,'');assert.equal(get('kiosk-feedback').open,false);
  console.log('kiosk_feedback_frontend=passed (horario oficial, tipo, alerta, limpeza, texto seguro)');
})().catch(error=>{console.error(error);process.exitCode=1;});
