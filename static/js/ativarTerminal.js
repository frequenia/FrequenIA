const activationForm = document.getElementById("activation-form");
const credentialInput = document.getElementById("credential");
const activationButton = document.getElementById("activate-button");
const activationStatus = document.getElementById("activation-status");

activationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const credential = credentialInput.value.trim();
  if (credential.length < 32) {
    activationStatus.textContent = "Informe a credencial completa fornecida pelo administrador.";
    return;
  }
  activationButton.disabled = true;
  activationStatus.textContent = "Validando terminal…";
  try {
    const response = await fetch("/api/quiosque/ativar", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credencial: credential }),
    });
    credentialInput.value = "";
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      activationStatus.textContent = body.erro || "Não foi possível ativar o terminal.";
      return;
    }
    window.location.replace("/quiosque/ponto");
  } catch (_) {
    credentialInput.value = "";
    activationStatus.textContent = "Não foi possível conectar ao servidor. Verifique se o backend está ligado.";
  } finally {
    activationButton.disabled = false;
  }
});
