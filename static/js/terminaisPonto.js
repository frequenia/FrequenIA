const createForm = document.getElementById("create-terminal-form");
const terminalName = document.getElementById("terminal-name");
const createButton = document.getElementById("create-terminal-button");
const statusText = document.getElementById("terminal-status");
const credentialPanel = document.getElementById("new-credential");
const credentialValue = document.getElementById("credential-value");
const terminalList = document.getElementById("terminal-list");

async function terminalRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.erro || "Não foi possível concluir a operação.");
  return body;
}

async function loadTerminals() {
  try {
    const result = await terminalRequest("/api/admin/terminais-ponto");
    terminalList.replaceChildren();
    if (!result.terminais.length) {
      terminalList.textContent = "Nenhum terminal cadastrado.";
      return;
    }
    for (const item of result.terminais) {
      const row = document.createElement("div");
      row.className = "terminal-row";
      const details = document.createElement("span");
      details.textContent = `${item.nome} — ${item.status === "ativo" ? "Ativo" : "Revogado"}`;
      row.append(details);
      if (item.status === "ativo") {
        const revokeButton = document.createElement("button");
        revokeButton.type = "button";
        revokeButton.className = "btn-secondary";
        revokeButton.textContent = "Revogar";
        revokeButton.addEventListener("click", async () => {
          if (!window.confirm(`Revogar o terminal "${item.nome}"? Ele deixará de registrar ponto imediatamente.`)) return;
          revokeButton.disabled = true;
          try {
            await terminalRequest(`/api/admin/terminais-ponto/${encodeURIComponent(item.id)}/revogar`, {
              method: "POST",
              body: "{}",
            });
            statusText.textContent = "Terminal revogado.";
            await loadTerminals();
          } catch (error) {
            statusText.textContent = error.message;
            revokeButton.disabled = false;
          }
        });
        row.append(revokeButton);
      }
      terminalList.append(row);
    }
  } catch (error) {
    statusText.textContent = error.message;
  }
}

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = terminalName.value.trim();
  if (!name) return;
  createButton.disabled = true;
  credentialPanel.hidden = true;
  credentialValue.value = "";
  try {
    const result = await terminalRequest("/api/admin/terminais-ponto", {
      method: "POST",
      body: JSON.stringify({ nome: name }),
    });
    credentialValue.value = result.terminal.credencial;
    credentialPanel.hidden = false;
    terminalName.value = "";
    statusText.textContent = "Terminal criado. Copie a credencial antes de sair desta página.";
    await loadTerminals();
  } catch (error) {
    statusText.textContent = error.message;
  } finally {
    createButton.disabled = false;
  }
});

document.getElementById("copy-credential").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(credentialValue.value);
    statusText.textContent = "Credencial copiada. Cole-a somente na tela de ativação do computador autorizado.";
  } catch (_) {
    credentialValue.select();
    statusText.textContent = "Selecione e copie a credencial exibida.";
  }
});

window.addEventListener("pagehide", () => { credentialValue.value = ""; });
loadTerminals();
