const form = document.getElementById("companyForm");
const button = document.getElementById("saveCompany");
const message = document.getElementById("formMessage");

function digits(value, limit) {
  return value.replace(/\D/g, "").slice(0, limit);
}

function formatCpf(value) {
  return digits(value, 11)
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
}

function formatCnpj(value) {
  return digits(value, 14)
    .replace(/(\d{2})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1/$2")
    .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
}

function formatPhone(value) {
  const numbers = digits(value, 11);
  return numbers.length > 10
    ? numbers.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3")
    : numbers.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3");
}

function validCpf(value) {
  const cpf = digits(value, 11);
  if (cpf.length !== 11 || /^(\d)\1+$/.test(cpf)) return false;
  const numbers = [...cpf].map(Number);
  const digit = (length) => {
    const sum = numbers.slice(0, length).reduce(
      (total, number, index) => total + number * (length + 1 - index),
      0,
    );
    const remainder = sum % 11;
    return remainder < 2 ? 0 : 11 - remainder;
  };
  return digit(9) === numbers[9] && digit(10) === numbers[10];
}

function showMessage(text, kind = "error") {
  message.textContent = text;
  message.className = `form-message ${kind}`;
  message.hidden = !text;
}

document.getElementById("cnpj").addEventListener("input", (event) => {
  event.target.value = formatCnpj(event.target.value);
});
document.getElementById("adminCpf").addEventListener("input", (event) => {
  event.target.value = formatCpf(event.target.value);
});
document.getElementById("adminTelefone").addEventListener("input", (event) => {
  event.target.value = formatPhone(event.target.value);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showMessage("");
  if (!form.reportValidity()) return;
  if (!validCpf(document.getElementById("adminCpf").value)) {
    showMessage("CPF do primeiro administrador é inválido.");
    document.getElementById("adminCpf").focus();
    return;
  }

  const payload = {
    cnpj: document.getElementById("cnpj").value,
    razao: document.getElementById("razao").value.trim(),
    administrador: {
      nome: document.getElementById("adminNome").value.trim(),
      cpf: document.getElementById("adminCpf").value,
      email: document.getElementById("adminEmail").value.trim(),
      telefone: document.getElementById("adminTelefone").value.trim(),
    },
  };

  button.disabled = true;
  button.textContent = "Cadastrando...";
  try {
    const response = await fetch("/cadastrar_empresa", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.mensagem || "Não foi possível cadastrar a empresa.");
    const companyId = result.empresa.id;
    const warning = result.convite?.status === "falhou";
    showMessage(`${result.mensagem} Matrícula: ${result.matricula}.`, warning ? "warning" : "success");
    window.setTimeout(() => {
      window.location.href = `/plataforma?empresa=${encodeURIComponent(companyId)}`;
    }, warning ? 2200 : 900);
  } catch (error) {
    showMessage(error.message);
    button.disabled = false;
    button.textContent = "Cadastrar empresa e enviar convite";
  }
});
