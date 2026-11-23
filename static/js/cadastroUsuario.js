const selectEmpresa = document.getElementById("empresa");
const empresaNome = document.getElementById("empresa_nome");
const selectUnidade = document.getElementById("unidade");
const selectEquipe = document.getElementById("equipe");
const selectCargo = document.getElementById("cargo");

function initializeStyledSelects() {
  document.querySelectorAll(".cadastro-page select").forEach((select) => {
    const wrapper = document.createElement("div");
    wrapper.className = "custom-select";
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
    wrapper.insertBefore(trigger, select);
    wrapper.append(menu);

    const refresh = () => {
      trigger.disabled = select.disabled;
      const selected = select.options[select.selectedIndex];
      trigger.querySelector(".select-label").textContent = selected?.textContent || "Selecione";
      menu.replaceChildren();
      [...select.options].forEach((option) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "select-option";
        item.dataset.value = option.value;
        item.textContent = option.textContent;
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", String(option.value === select.value));
        if (option.value === select.value) item.classList.add("selected");
        item.addEventListener("click", () => {
          select.value = option.value;
          select.dispatchEvent(new Event("change", { bubbles: true }));
          wrapper.classList.remove("open");
          trigger.setAttribute("aria-expanded", "false");
          trigger.focus();
        });
        menu.append(item);
      });
    };

    trigger.addEventListener("click", () => {
      if (select.disabled) return;
      const opening = !wrapper.classList.contains("open");
      document.querySelectorAll(".custom-select.open").forEach((item) => item.classList.remove("open"));
      wrapper.classList.toggle("open", opening);
      trigger.setAttribute("aria-expanded", String(opening));
    });
    select.addEventListener("change", refresh);
    new MutationObserver(refresh).observe(select, { childList: true, attributes: true, attributeFilter: ["disabled"] });
    refresh();
  });

  document.addEventListener("click", (event) => {
    document.querySelectorAll(".cadastro-page .custom-select.open").forEach((wrapper) => {
      if (wrapper.contains(event.target)) return;
      wrapper.classList.remove("open");
      wrapper.querySelector(".select-trigger").setAttribute("aria-expanded", "false");
    });
  });
}

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
  const empresas = await response.json();
  if (!response.ok || empresas.length !== 1) {
    empresaNome.value = "Empresa não disponível";
    return;
  }
  selectEmpresa.value = empresas[0].id;
  empresaNome.value = empresas[0].nome;
  await carregarEstruturaEmpresa();
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

function verificarCPF(value) {
  return CadastroValidation.cpfValid(value);
}

function limparCadastro() {
  const form = document.getElementById("formCadastro");
  const empresaId = selectEmpresa.value;
  const nomeEmpresa = empresaNome.value;
  form.reset();

  selectEmpresa.value = empresaId;
  empresaNome.value = nomeEmpresa;
  selectUnidade.value = "";
  preencherSelect(selectEquipe, []);
  selectEquipe.value = "";
  selectEquipe.disabled = true;
  selectCargo.value = "";

  form.querySelectorAll("select").forEach((select) => {
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

async function cadastrarUsuario() {
  const form = document.getElementById("formCadastro");
  if (!CadastroValidation.validate(form)) return;

  const payload = {
    nome: document.getElementById("nome").value.trim(),
    email: document.getElementById("email").value.trim(),
    telefone: document.getElementById("telefone").value.trim(),
    cpf: document.getElementById("cpf").value,
    empresa_id: selectEmpresa.value,
    unidade_id: selectUnidade.value,
    equipe_id: selectEquipe.value,
    cargo_id: selectCargo.value,
    perfil: document.getElementById("perfil").value,
    tipo_contrato: document.getElementById("tipo_contrato").value,
    data_admissao: document.getElementById("data_admissao").value,
    carga_horaria_semanal: document.getElementById("carga_horaria").value,
  };

  try {
  const response = await fetch("/cadastrar_usuario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) { if (result.matricula) result.mensagem = `${result.mensagem || "Cadastro realizado com pendência."} Matrícula: ${result.matricula}.`; CadastroValidation.serverErrors(form, result); return; }
  const matricula = result.matricula ? ` Matrícula: ${result.matricula}.` : "";
  alert((result.mensagem || (response.ok ? "Cadastro concluído." : "Não foi possível cadastrar.")) + matricula);
  if (response.ok) limparCadastro();
  } catch { CadastroValidation.serverErrors(form, {mensagem: "Falha de conexão. Confira se o cadastro foi salvo antes de tentar novamente."}); }
}

selectUnidade.addEventListener("change", carregarEquipes);
document.getElementById("formCadastro").addEventListener("submit", event => { event.preventDefault(); cadastrarUsuario(); });
document.getElementById("limparCadastro").addEventListener("click", limparCadastro);
initializeStyledSelects();
carregarEmpresas();
