const selectEmpresa = document.getElementById("empresa");
const selectUnidade = document.getElementById("unidade");
const selectEquipe = document.getElementById("equipe");
const selectCargo = document.getElementById("cargo");

function preencherSelect(select, items, placeholder = "Selecione") {
  select.innerHTML = `<option value="">${placeholder}</option>`;
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.nome;
    select.appendChild(option);
  });
  select.disabled = false;
}

async function carregarEmpresas() {
  const response = await fetch("/listarEmpresas");
  preencherSelect(selectEmpresa, await response.json());
}

async function carregarEstruturaEmpresa() {
  const empresaId = selectEmpresa.value;
  preencherSelect(selectUnidade, []);
  preencherSelect(selectEquipe, []);
  preencherSelect(selectCargo, []);
  selectUnidade.disabled = selectEquipe.disabled = selectCargo.disabled = true;
  if (!empresaId) return;

  const [unidadesResponse, cargosResponse] = await Promise.all([
    fetch(`/listar_unidades?empresa_id=${encodeURIComponent(empresaId)}`),
    fetch(`/listar_cargos?empresa_id=${encodeURIComponent(empresaId)}`),
  ]);
  preencherSelect(selectUnidade, await unidadesResponse.json());
  preencherSelect(selectCargo, await cargosResponse.json());
}

async function carregarEquipes() {
  const empresaId = selectEmpresa.value;
  const unidadeId = selectUnidade.value;
  preencherSelect(selectEquipe, []);
  selectEquipe.disabled = true;
  if (!empresaId || !unidadeId) return;

  const response = await fetch(`/listar_equipes?empresa_id=${encodeURIComponent(empresaId)}&unidade_id=${encodeURIComponent(unidadeId)}`);
  preencherSelect(selectEquipe, await response.json());
}

function mascaraCPF(campo) {
  let cpf = campo.value.replace(/\D/g, "").slice(0, 11);
  cpf = cpf.replace(/(\d{3})(\d)/, "$1.$2");
  cpf = cpf.replace(/(\d{3})(\d)/, "$1.$2");
  cpf = cpf.replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  campo.value = cpf;
}

function mascaraTelefone(campo) {
  let telefone = campo.value.replace(/\D/g, "").slice(0, 11);
  telefone = telefone.replace(/^(\d{2})(\d)/, "($1) $2");
  telefone = telefone.length > 10
    ? telefone.replace(/(\d{5})(\d{4})$/, "$1-$2")
    : telefone.replace(/(\d{4})(\d{4})$/, "$1-$2");
  campo.value = telefone;
}

function verificarCPF(value) {
  const cpf = value.replace(/\D/g, "");
  if (cpf.length !== 11 || /^(\d)\1+$/.test(cpf)) return false;
  const numbers = cpf.split("").map(Number);
  let sum = numbers.slice(0, 9).reduce((total, number, index) => total + number * (10 - index), 0);
  const first = sum % 11 < 2 ? 0 : 11 - (sum % 11);
  sum = numbers.slice(0, 10).reduce((total, number, index) => total + number * (11 - index), 0);
  const second = sum % 11 < 2 ? 0 : 11 - (sum % 11);
  return first === numbers[9] && second === numbers[10];
}

async function cadastrarUsuario() {
  if (!document.getElementById("formCadastro").reportValidity()) return;
  if (!verificarCPF(document.getElementById("cpf").value)) {
    alert("CPF inválido.");
    return;
  }

  const payload = {
    nome: document.getElementById("nome").value.trim(),
    email: document.getElementById("email").value.trim(),
    telefone: document.getElementById("telefone").value.trim(),
    cpf: document.getElementById("cpf").value,
    senha: document.getElementById("senha").value,
    empresa_id: selectEmpresa.value,
    unidade_id: selectUnidade.value,
    equipe_id: selectEquipe.value,
    cargo_id: selectCargo.value,
    matricula: document.getElementById("matricula").value.trim(),
    perfil: document.getElementById("perfil").value,
    tipo_contrato: document.getElementById("tipo_contrato").value,
    data_admissao: document.getElementById("data_admissao").value,
    carga_horaria_semanal: document.getElementById("carga_horaria").value,
  };

  const response = await fetch("/cadastrar_usuario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  alert(result.mensagem || (response.ok ? "Cadastro concluído." : "Não foi possível cadastrar."));
  if (response.ok) document.getElementById("formCadastro").reset();
}

selectEmpresa.addEventListener("change", carregarEstruturaEmpresa);
selectUnidade.addEventListener("change", carregarEquipes);
carregarEmpresas();
