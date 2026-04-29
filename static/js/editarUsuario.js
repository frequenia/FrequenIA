async function carregarCargos() {
  const res = await fetch("/listar_cargos");
  const cargos = await res.json();

  const select = document.getElementById("cargo");
    const cargoAtual = select.dataset.cargo; // pega o cargo atual do usuário
    
    console.log("Cargo atual:", cargoAtual); // <- adiciona isso
    console.log("Cargos:", cargos);

  cargos.forEach((cargo) => {
    const option = document.createElement("option");
    option.value = cargo.id;
    option.textContent = cargo.nome;
    if (cargo.id == cargoAtual) option.selected = true;
    select.appendChild(option);
  });
}

async function carregarSetores() {
  const res = await fetch("/listar_setores");
  const setores = await res.json();

  const select = document.getElementById("setor");
  const setorAtual = select.dataset.setor;

  setores.forEach((setor) => {
    const option = document.createElement("option");
    option.value = setor.id;
    option.textContent = setor.nome;
    if (setor.id == setorAtual) option.selected = true;
    select.appendChild(option);
  });
}

async function carregarTipoContrato() {
  const select = document.getElementById("tipo_contrato");
  const tipoAtual = select.dataset.contrato;

  const opcoes = [
    { value: "clt", label: "CLT" },
    { value: "pj", label: "PJ" },
    { value: "estagiario", label: "Estágio" },
    { value: "temporario", label: "Temporário" },
  ];

  opcoes.forEach((op) => {
    const option = document.createElement("option");
    option.value = op.value;
    option.textContent = op.label;
    if (op.value == tipoAtual) option.selected = true;
    select.appendChild(option);
  });
}

carregarCargos();
carregarSetores();
carregarTipoContrato();


function alterarDados() {
  document.querySelectorAll(".campo-editavel").forEach((el) => {
    if (el.tagName === "INPUT") {
      el.readOnly = false;
    } else {
      el.disabled = false;
    }
  });
  document.getElementById("btnSalvar").style.display = "inline-block";
}

function bloquearCampos() {
  document.querySelectorAll(".campo-editavel").forEach((el) => {
    if (el.tagName === "INPUT") {
      el.readOnly = true;
    }

    if (el.tagName === "SELECT") {
      el.disabled = true;
    }
  });
}

async function salvarAlteracoes() {
  const nome = document.getElementById("nome").value;
  const email = document.getElementById("email").value;
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");

  const res = await fetch("/atualizar_usuario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: id,
      nome: nome,
      email: email,
      telefone: document.getElementById("telefone").value,
      cargo_id: document.getElementById("cargo").value,
      setor_id: document.getElementById("setor").value,
      tipo_contrato: document.getElementById("tipo_contrato").value,
      data_admissao: document.getElementById("data_admissao").value,
      carga_horaria: document.getElementById("carga_horaria").value,
    }),
  });

  const data = await res.json();

  if (data.status === "ok") {
    alert("Campos atualizados com sucesso!");
    bloquearCampos();
    document.getElementById("btnSalvar").style.display = "none";
    window.location.href = "/gerenciarUsuario";
  } else {
    alert("Erro ao atualizar");
  }
}

async function deletarUsuario() {
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");

  const confirmar = confirm(
    "Tem certeza que deseja excluir este usuário? Esta ação não pode ser desfeita.",
  );
  if (!confirmar) return;

  const res = await fetch("/deletar_usuario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: id }),
  });

  const data = await res.json();

  if (data.status === "ok") {
    alert("Usuário excluído com sucesso!");
    window.location.href = "/gerenciarUsuario";
  } else {
    alert("Erro ao excluir usuário: " + data.mensagem);
  }
}