const createForm = document.getElementById("create-terminal-form");
const terminalName = document.getElementById("terminal-name");
const createButton = document.getElementById("create-terminal-button");
const statusText = document.getElementById("terminal-status");
const credentialPanel = document.getElementById("new-credential");
const credentialValue = document.getElementById("credential-value");
const terminalList = document.getElementById("terminal-list");
const terminalSearch = document.getElementById("terminal-search");
const terminalStatusFilter = document.getElementById("terminal-status-filter");
let allTerminals = [];

function normalizeTerminalName(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

function renderTerminals() {
  const searchTerm = normalizeTerminalName(terminalSearch.value);
  const selectedStatus = terminalStatusFilter.value;
  const filtered = allTerminals.filter((item) => {
    const nameMatches = normalizeTerminalName(item.nome).includes(searchTerm);
    const statusMatches = selectedStatus === "todos" || item.status === selectedStatus;
    return nameMatches && statusMatches;
  });

  terminalList.replaceChildren();
  if (!filtered.length) {
    const empty = document.createElement("p");
    empty.className = "terminal-empty";
    empty.textContent = allTerminals.length ? "Nenhum terminal corresponde a essa busca." : "Nenhum terminal cadastrado.";
    terminalList.append(empty);
    return;
  }

  for (const item of filtered) {
    const row = document.createElement("div");
    row.className = "terminal-row";
    const info = document.createElement("div");
    info.className = "terminal-info";
    const name = document.createElement("strong");
    name.className = "terminal-name";
    name.textContent = item.nome;
    const status = document.createElement("span");
    status.className = `terminal-state${item.status === "ativo" ? "" : " revoked"}`;
    status.textContent = item.status === "ativo" ? "Ativo" : "Revogado";
    info.append(name, status);
    row.append(info);
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
}

function setupTerminalStatusFilter() {
  const select = terminalStatusFilter;
  const wrapper = document.createElement("div");
  wrapper.className = "custom-select terminal-status-select";
  select.parentNode.insertBefore(wrapper, select);
  wrapper.append(select);
  select.classList.add("native-select");

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "select-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  trigger.innerHTML = '<span class="select-label"></span><span class="select-chevron" aria-hidden="true"></span>';
  const menu = document.createElement("div");
  menu.className = "select-menu";
  menu.setAttribute("role", "listbox");

  const syncSelection = () => {
    trigger.querySelector(".select-label").textContent = select.options[select.selectedIndex].textContent;
    menu.querySelectorAll(".select-option").forEach((option) => {
      const selected = option.dataset.value === select.value;
      option.classList.toggle("selected", selected);
      option.setAttribute("aria-selected", String(selected));
    });
  };
  [...select.options].forEach((option) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "select-option";
    item.dataset.value = option.value;
    item.textContent = option.textContent;
    item.setAttribute("role", "option");
    item.addEventListener("click", () => {
      select.value = option.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      wrapper.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
      trigger.focus();
    });
    menu.append(item);
  });
  wrapper.insertBefore(trigger, select);
  wrapper.append(menu);
  trigger.addEventListener("click", () => {
    const opening = !wrapper.classList.contains("open");
    document.querySelectorAll(".custom-select.open").forEach((other) => other.classList.remove("open"));
    wrapper.classList.toggle("open", opening);
    trigger.setAttribute("aria-expanded", String(opening));
  });
  select.addEventListener("change", () => { syncSelection(); renderTerminals(); });
  document.addEventListener("click", (event) => {
    if (wrapper.contains(event.target)) return;
    wrapper.classList.remove("open");
    trigger.setAttribute("aria-expanded", "false");
  });
  syncSelection();
}

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
    allTerminals = Array.isArray(result.terminais) ? result.terminais : [];
    renderTerminals();
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

terminalSearch.addEventListener("input", renderTerminals);
setupTerminalStatusFilter();

window.addEventListener("pagehide", () => { credentialValue.value = ""; });
loadTerminals();
