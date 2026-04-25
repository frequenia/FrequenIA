// coloca a formatação dos pontos e traço no CPF
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

// alterna entre exibir/ocultar a senha
function mostrarSenha() {
  const campo = document.getElementById("senha");

  if (campo.type === "password") {
    campo.type = "text";
  } else {
    campo.type = "password";
  }
}

// verifica se o CPF é válido
function verificarCPF() {
  let campoCPF = document.getElementById("cpf").value;
  let soma = 0;
  campoCPF = campoCPF.replace(/\D/g, "");
  let CPF = campoCPF.split("").map(Number);

  for (let i = 0; i <= 8; i++) {
    soma += CPF[i] * (10 - i);
  }

  let digito1 = soma % 11;

  if (digito1 < 2) {
    digito1 = 0;
  } else {
    digito1 = 11 - digito1;
  }

  soma = 0;

  for (let i = 0; i <= 9; i++) {
    soma += CPF[i] * (11 - i);
  }

  let digito2 = soma % 11;

  if (digito2 < 2) {
    digito2 = 0;
  } else {
    digito2 = 11 - digito2;
  }

  if (digito1 == CPF[9] && digito2 == CPF[10]) {
    return true;
  } else {
    window.alert("CPF inválido. Tente novamente.");
    return false;
  }
}

// acessa o sistema
function login(event) {
  if (event) event.preventDefault();

  const campoCPF = document.getElementById("cpf");
  const campoSenha = document.getElementById("senha");

  if (campoCPF.value === "" || campoSenha.value === "") {
    alert("Foram encontrados campos vazios. Tente novamente.");
    return;
  }

  if (!verificarCPF()) {
    return;
  }

  const cpf = campoCPF.value.replace(/\D/g, "");
  const senha = campoSenha.value;

  fetch("/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({ cpf, senha }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.ok) {
        window.location.href = "/menu";
      } else {
        alert(data.erro || "Erro no login");
      }
    })
    .catch((error) => {
      alert("Erro ao conectar com o servidor.");
    });
}
// Inicializar EmailJS
emailjs.init("j2V8vMJBNoT3bmpRt");

function toggleSenha(el) {
  const box = el.closest(".password-box");
  const input = box.querySelector("input");

  if (input.type === "password") {
    input.type = "text";
    el.classList.remove("show"); // visível = sem risco
  } else {
    input.type = "password";
    el.classList.add("show"); // oculto = olho riscado
  }
}

function gerarCodigo() {
  return Math.floor(100000 + Math.random() * 900000).toString();
}

async function enviarCodigo() {
  const email = document.getElementById("email").value;

  const response = await fetch("/enviar-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });

  const data = await response.json();

  if (response.ok) {
    sessionStorage.setItem("email", email);

    // Envia o token por email
    await emailjs.send("worksync_services", "template_0weu91p", {
      to_email: email,
      token: data.token,
    });

    window.location.href = "/inserirToken";
  } else {
    alert(data.erro);
  }
}