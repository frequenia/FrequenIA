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

carregarCargos();

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
