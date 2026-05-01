// ==============================================================================================================
// FUNÇÕES RESPONSÁVEIS POR CARREGAR E EXIBIR DINAMICAMENTE CARGOS E SETORES NO FORMULÁRIO DE CADASTRO DE USUÁRIO
//===============================================================================================================

async function carregarCargos() {
  const select = document.getElementById("cargo");

  const res = await fetch("http://127.0.0.1:5000/listar_cargos");
  const cargos = await res.json();

  select.innerHTML = '<option value="">Selecione</option>';

  cargos.forEach((cargo) => {
    const option = document.createElement("option");
    option.value = cargo.id;
    option.textContent = cargo.nome;
    select.appendChild(option);
  });
}

async function carregarSetores() {
  const select = document.getElementById("setor");

  const res = await fetch("http://127.0.0.1:5000/listar_setores");
  const setores = await res.json();

  select.innerHTML = '<option value="">Selecione</option>';

  setores.forEach((setor) => {
    const option = document.createElement("option");
    option.value = setor.id;
    option.textContent = setor.nome;
    select.appendChild(option);
  });
}

window.onload = function() {
  carregarCargos();
  carregarSetores();
};


function toggleDia(id) {
  const dia = document.getElementById(id);

  if (dia.style.display === "none") {
    dia.style.display = "grid";
  } else {
    dia.style.display = "none";
  }
}

function alternarJornada() {
  const tipo = document.getElementById("tipoJornada").value;

  const padrao = document.getElementById("jornadaPadrao");
  const manual = document.getElementById("jornadaManual");

  if (tipo === "padrao") {
    padrao.style.display = "block";
    manual.style.display = "none";
  } else {
    padrao.style.display = "none";
    manual.style.display = "block";
  }
}

function formatarCPF(cpf) {
  cpf = cpf.replace(/\D/g, ""); // remove tudo que não é número

  if (cpf.length === 11) {
    cpf = cpf.replace(/(\d{3})(\d)/, "$1.$2");
    cpf = cpf.replace(/(\d{3})(\d)/, "$1.$2");
    cpf = cpf.replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  }

  return cpf;
}

function mascaraCPF(campo) {
  let cpf = campo.value.replace(/\D/g, "");
  if (cpf.length > 11) {
    cpf = cpf.substring(0, 11);
  }
  cpf = cpf.replace(/(\d{3})(\d)/, "$1.$2");
  cpf = cpf.replace(/(\d{3})(\d)/, "$1.$2");
  cpf = cpf.replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  campo.value = cpf;
}

function mascaraTelefone(campo) {
  let telefone = campo.value.replace(/\D/g, "");

  // limita a 11 dígitos
  if (telefone.length > 11) {
    telefone = telefone.substring(0, 11);
  }

  // aplica máscara
  if (telefone.length > 0) {
    telefone = telefone.replace(/^(\d{2})(\d)/, "($1) $2");
  }

  if (telefone.length > 10) {
    telefone = telefone.replace(/(\d{5})(\d{4})$/, "$1-$2");
  } else {
    telefone = telefone.replace(/(\d{4})(\d{4})$/, "$1-$2");
  }

  campo.value = telefone;
}

function verificarCPF(cpfInput) {
  let soma = 0;

  cpfInput = cpfInput.replace(/\D/g, "");
  let CPF = cpfInput.split("").map(Number);

  if (CPF.length !== 11) return false;

  if (/^(\d)\1+$/.test(cpfInput)) return false;

  for (let i = 0; i <= 8; i++) {
    soma += CPF[i] * (10 - i);
  }

  let digito1 = soma % 11;
  digito1 = digito1 < 2 ? 0 : 11 - digito1;

  soma = 0;

  for (let i = 0; i <= 9; i++) {
    soma += CPF[i] * (11 - i);
  }

  let digito2 = soma % 11;
  digito2 = digito2 < 2 ? 0 : 11 - digito2;

  return digito1 == CPF[9] && digito2 == CPF[10];
}

async function cadastrarUsuario() {
  const camposObrigatorios = [
    "nome",
    "email",
    "cpf",
    "telefone",
    "cargo",
    "setor",
    "tipo_perfil",
    "tipo_contrato",
    "data_admissao",
    "carga_horaria",
  ];

  for (let id of camposObrigatorios) {
    const valor = document.getElementById(id).value.trim();
    if (!valor) {
      alert(`O campo ${id} é obrigatório!`);
      document.getElementById(id).focus();
      return;
    }
  }

  // validação do nome
  const nomeInput = document.getElementById("nome").value.trim();
  if (!/^[A-Za-zÀ-ÿ\s]+$/.test(nomeInput)) {
    alert("O nome deve conter apenas letras!");
    document.getElementById("nome").focus();
    return;
  }

  // validação do email
  const email = document.getElementById("email").value.trim();
  if (!email.includes("@") || email.startsWith("@")) {
    alert("O email deve conter '@' e não pode começar com ele!");
    document.getElementById("email").focus();
    return;
  }

  // validação do telefone
  const telefoneLimpo = document.getElementById("telefone").value.replace(/\D/g, "");
  if (telefoneLimpo.length !== 11) {
    alert("O telefone deve conter 11 dígitos (DDD + número)!");
    document.getElementById("telefone").focus();
    return;
  }

  const cpfInput = document.getElementById("cpf").value;

  if (!verificarCPF(cpfInput)) {
    alert("CPF inválido!");
    document.getElementById("cpf").focus();
    return;
  }

  const telefoneFormatado = `(${telefoneLimpo.substring(0, 2)}) ${telefoneLimpo.substring(2, 7)}-${telefoneLimpo.substring(7)}`;

  // monta horários conforme tipo de jornada
  const mapeamentoDias = {
    domingo: 0,
    segunda: 1,
    terca: 2,
    quarta: 3,
    quinta: 4,
    sexta: 5,
    sabado: 6,
  };

  let horarios = [];
  const tipoJornada = document.getElementById("tipoJornada").value;

  if (tipoJornada === "padrao") {
    const diasSelecionados = [];
    document
      .querySelectorAll("#jornadaPadrao input[type=checkbox]:checked")
      .forEach((dia) => {
        diasSelecionados.push(parseInt(dia.value));
      });

    if (diasSelecionados.length === 0) {
      alert("Selecione pelo menos um dia da semana!");
      return;
    }

    const inicio_expediente =
      document.getElementById("inicio_expediente").value;
    const inicio_intervalo = document.getElementById("inicio_intervalo").value;
    const termino_intervalo =
      document.getElementById("termino_intervalo").value;
    const termino_expediente =
      document.getElementById("termino_expediente").value;

    if (!inicio_expediente || !termino_expediente) {
      alert("Preencha os horários!");
      return;
    }

    horarios = diasSelecionados.map((dia) => ({
      dia_semana: dia,
      inicio_expediente,
      inicio_intervalo,
      termino_intervalo,
      termino_expediente,
    }));
  } else {
    Object.entries(mapeamentoDias).forEach(([nome, numero]) => {
      const div = document.getElementById(nome);
      if (div && div.style.display !== "none") {
        horarios.push({
          dia_semana: numero,
          inicio_expediente: document.getElementById(
            `${nome}_inicio_expediente`,
          ).value,
          inicio_intervalo: document.getElementById(`${nome}_inicio_intervalo`)
            .value,
          termino_intervalo: document.getElementById(
            `${nome}_termino_intervalo`,
          ).value,
          termino_expediente: document.getElementById(
            `${nome}_termino_expediente`,
          ).value,
        });
      }
    });

    if (horarios.length === 0) {
      alert("Selecione pelo menos um dia na jornada manual!");
      return;
    }
  }

  const dados = {
    nome: document.getElementById("nome").value.trim().toUpperCase(),
    email: document.getElementById("email").value,
    telefone: telefoneFormatado,
    cpf: formatarCPF(document.getElementById("cpf").value),
    cargo_id: parseInt(document.getElementById("cargo").value),
    setor_id: parseInt(document.getElementById("setor").value),
    tipo_perfil: document.getElementById("tipo_perfil").value,
    tipo_contrato: document.getElementById("tipo_contrato").value,
    data_admissao: document.getElementById("data_admissao").value,
    carga_horaria: document.getElementById("carga_horaria").value,
    matricula: "AUTO-" + Math.floor(Math.random() * 10000),
    jornada: tipoJornada,
    horarios: horarios,
  };

  const res = await fetch("http://127.0.0.1:5000/cadastrar_usuario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dados),
  });

  const json = await res.json();

  if (json.status === "ok") {
    alert(json.mensagem);
    const form = document.getElementById("formCadastro");
    form.reset();

    document.getElementById("jornadaPadrao").style.display = "block";
    document.getElementById("jornadaManual").style.display = "none";
    document.getElementById("tipoJornada").value = "padrao";

    document.querySelectorAll(".dia-manual").forEach((div) => {
      div.style.display = "none";
    });

    document.getElementById("nome").focus();
  } else {
    alert("Erro: " + json.mensagem);
  }
}