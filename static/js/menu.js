/* ============================================================
   menu.js — Funcionalidades do Menu Principal
   ============================================================ */

// ─── SIDEBAR NAVIGATION ───
const links = [...document.querySelectorAll(".sidebar-nav a")];
const painel = document.querySelector('iframe[name="conteudo"]');
const localizacao = document.getElementById("topbarLocation");

function atualizarLocalizacao(caminho) {
  if (!localizacao) return;
  const atual = links.find(link => link.pathname === caminho);
  links.forEach(link => {
    link.parentElement.classList.toggle("active", link === atual);
    if (link === atual) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  localizacao.replaceChildren();
  const titulo = atual?.textContent.trim() || (caminho === "/perfil" ? "Meu perfil" : "");
  if (!titulo) return;
  if (["/controleponto", "/ocorrencias", "/ocorrencias/falhas-faciais", "/jornadas", "/meu-ponto", "/minhas-solicitacoes"].includes(caminho)) {
    const grupo = document.createElement("span");
    grupo.className = "topbar-section";
    grupo.textContent = "Ponto / ";
    localizacao.append(grupo);
  }
  localizacao.append(titulo);
}

if (painel) {
  atualizarLocalizacao(new URL(painel.src).pathname);
  painel.addEventListener("load", () => {
    try {
      atualizarLocalizacao(painel.contentWindow.location.pathname);
    } catch {
      atualizarLocalizacao("");
    }
  });
}

// ─── RELÓGIO E DATA ───
async function atualizarRelogio() {
  const resposta = await fetch("/hora-servidor");
  const dados = await resposta.json();

  document.getElementById("hora").textContent = dados.hora;
  document.getElementById("data").textContent = `${dados.dia}, ${dados.data}`;
}

setInterval(atualizarRelogio, 500);
atualizarRelogio();


// ─── PROFILE LINK ───
function atualizarPerfil() {
  const nome = usuarioNome || "Usuário";
  const foto = usuarioFoto || null;

  // Calcular iniciais
  const iniciais = nome
    .split(" ")
    .map(n => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  // Atualizar avatar
  const avatar = document.getElementById("profileAvatar");
  document.getElementById("profileInitials").textContent = iniciais;

  // Atualizar nome
  document.getElementById("profileName").textContent = nome;

  // Se houver foto, usar como background
  if (foto) {
    avatar.style.backgroundImage = `url('${foto}')`;
    avatar.style.backgroundSize = "cover";
    avatar.style.backgroundPosition = "center";
    avatar.innerHTML = "";
  }
}

atualizarPerfil();

// ─── TEMA GLOBAL ───
function aplicarTemaGlobal() {
  const tema = localStorage.getItem("tema") || "light";

  if (tema === "dark") {
    document.body.classList.add("dark-mode");
  } else {
    document.body.classList.remove("dark-mode");
  }

  const iframe = document.querySelector("iframe");

  if (iframe) {
    iframe.onload = () => {
      const temaAtual = localStorage.getItem("tema") || "light";

      if (temaAtual === "dark") {
        iframe.contentWindow.document.body.classList.add("dark-mode");
      } else {
        iframe.contentWindow.document.body.classList.remove("dark-mode");
      }
    };
  }
}

aplicarTemaGlobal();

// ─── LOGOUT ───
const logoutDialog = document.getElementById("logoutDialog");
document.getElementById("openLogout")?.addEventListener("click", () => {
  logoutDialog.showModal();
});
