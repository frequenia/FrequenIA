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

function validCpf(value) {
  return CadastroValidation.cpfValid(value);
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
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showMessage("");
  if (!CadastroValidation.validate(form)) return;

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
    if (!response.ok) { CadastroValidation.serverErrors(form, result); throw new Error(result.mensagem || "Não foi possível cadastrar a empresa."); }
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
