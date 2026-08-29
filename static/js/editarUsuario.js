const form = document.getElementById("formCadastro");
const funcionarioId = form.dataset.funcionarioId;
const empresa = document.getElementById("empresa");
const unidade = document.getElementById("unidade");
const equipe = document.getElementById("equipe");
const cargo = document.getElementById("cargo");

function preencher(select, items, selectedValue) {
  select.innerHTML = '<option value="">Selecione</option>';
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.nome;
    option.selected = item.id === selectedValue;
    select.appendChild(option);
  });
}

async function carregarEmpresas() {
  const response = await fetch("/listarEmpresas");
  preencher(empresa, await response.json(), empresa.dataset.value);
  await carregarEstrutura(empresa.dataset.value, unidade.dataset.value, equipe.dataset.value, cargo.dataset.value);
  document.getElementById("perfil").value = document.getElementById("perfil").dataset.value;
  document.getElementById("tipo_contrato").value = document.getElementById("tipo_contrato").dataset.value;
}

async function carregarEstrutura(empresaId, unidadeAtual = "", equipeAtual = "", cargoAtual = "") {
  if (!empresaId) return;
  const [unidadesResponse, cargosResponse] = await Promise.all([
    fetch(`/listar_unidades?empresa_id=${encodeURIComponent(empresaId)}`),
    fetch(`/listar_cargos?empresa_id=${encodeURIComponent(empresaId)}`),
  ]);
  preencher(unidade, await unidadesResponse.json(), unidadeAtual);
  preencher(cargo, await cargosResponse.json(), cargoAtual);
  await carregarEquipes(empresaId, unidadeAtual, equipeAtual);
}

async function carregarEquipes(empresaId, unidadeId, equipeAtual = "") {
  if (!empresaId || !unidadeId) {
    preencher(equipe, [], "");
    return;
  }
  const response = await fetch(`/listar_equipes?empresa_id=${encodeURIComponent(empresaId)}&unidade_id=${encodeURIComponent(unidadeId)}`);
  preencher(equipe, await response.json(), equipeAtual);
}

function alterarDados() {
  document.querySelectorAll(".campo-editavel").forEach((element) => {
    element.readOnly = false;
    element.disabled = false;
  });
  document.getElementById("btnSalvar").style.display = "inline-block";
}

function bloquearCampos() {
  document.querySelectorAll(".campo-editavel").forEach((element) => {
    if (element.tagName === "SELECT") element.disabled = true;
    else element.readOnly = true;
  });
}

async function salvarAlteracoes() {
  if (!form.reportValidity()) return;
  const payload = {
    funcionario_id: funcionarioId,
    nome: document.getElementById("nome").value.trim(),
    email: document.getElementById("email").value.trim(),
    telefone: document.getElementById("telefone").value.trim(),
    cpf: document.getElementById("cpf").value,
    empresa_id: empresa.value,
    unidade_id: unidade.value,
    equipe_id: equipe.value,
    cargo_id: cargo.value,
    matricula: document.getElementById("matricula").value.trim(),
    perfil: document.getElementById("perfil").value,
    tipo_contrato: document.getElementById("tipo_contrato").value,
    data_admissao: document.getElementById("data_admissao").value,
    carga_horaria_semanal: document.getElementById("carga_horaria").value,
  };
  const response = await fetch("/atualizar_usuario", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
  const result = await response.json();
  alert(result.mensagem || (response.ok ? "Campos atualizados com sucesso." : "Não foi possível atualizar."));
  if (response.ok) {
    bloquearCampos();
    document.getElementById("btnSalvar").style.display = "none";
  }
}

async function atualizarStatus() {
  if (!confirm("Deseja alterar o status deste vínculo?")) return;
  const response = await fetch("/atualizar_status_usuario", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({funcionario_id: funcionarioId})});
  const result = await response.json();
  alert(result.mensagem || (response.ok ? "Status atualizado." : "Não foi possível atualizar o status."));
  if (response.ok) window.location.reload();
}

function atualizarTextoStatus() {
  const button = document.getElementById("btnStatus");
  button.textContent = button.dataset.status === "ativo" ? "Desativar vínculo" : "Reativar vínculo";
}

empresa.addEventListener("change", () => carregarEstrutura(empresa.value));
unidade.addEventListener("change", () => carregarEquipes(empresa.value, unidade.value));
carregarEmpresas();
atualizarTextoStatus();
