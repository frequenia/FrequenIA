// ELEMENTOS
const video = document.getElementById("video");
const btnCapturar = document.getElementById("btnCapturar");
const btnInstrucoes = document.getElementById("btnInstrucoes");
const btnFecharModal = document.getElementById("btnFecharModal");
const modal = document.getElementById("modal-instrucoes");
const contador = document.getElementById("contador");
const barra = document.getElementById("barra");

let fotosCapturadas = 0;
const maxFotos = 5;
let processando = false;
let cadastroIniciado = false;
let nomeGlobal = "";
let streamAtivo = null;

// =========================
// CARREGAR USUÁRIOS
// =========================
async function carregarUsuarios() {
    try {
        const res = await fetch("/listar_usuarios_select");
        const usuarios = await res.json();

        const select = document.getElementById("nome");

        usuarios.forEach((u) => {
            const option = document.createElement("option");
            option.value = u.id;
            option.textContent = u.nome;
            select.appendChild(option);
        });
    } catch (error) {
        console.error("Erro ao carregar usuários:", error);
        mostrarPopupErro("Erro ao carregar lista de usuários.");
    }
}

carregarUsuarios();

// =========================
// CAMERA
// =========================
function ligarCamera() {
    return new Promise((resolve, reject) => {
        navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 640 },
                height: { ideal: 480 },
                facingMode: "user"
            }
        })
            .then(stream => {
                streamAtivo = stream;
                video.srcObject = stream;
                video.play();

                const bg = document.querySelector(".camera-placeholder-bg");
                const status = document.querySelector(".camera-status");
                if (bg) bg.style.display = "none";
                if (status) status.style.display = "none";

                video.addEventListener("canplay", () => resolve(), { once: true });
            })
            .catch(error => {
                console.error("Erro câmera:", error);
                reject(error);
            });
    });
}

function desligarCamera() {
    if (streamAtivo) {
        streamAtivo.getTracks().forEach(track => track.stop());
        streamAtivo = null;
        video.srcObject = null;
    }

    const bg = document.querySelector(".camera-placeholder-bg");
    const status = document.querySelector(".camera-status");
    if (bg) bg.style.display = "";
    if (status) {
        status.style.display = "";
        status.textContent = "Câmera desativada";
    }
}

// =========================
// CAPTURA IMAGEM
// =========================
function capturarImagem() {
    if (!video || video.videoWidth === 0) return null;

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);

    return canvas.toDataURL("image/jpeg", 0.95);
}

// =========================
// CADASTRO
// =========================
async function cadastrar() {
    if (processando) return;
    processando = true;

    const select = document.getElementById("nome");
    const nome = select.options[select.selectedIndex].text;

    if (!nome || nome === "Selecione um usuário") {
        mostrarPopupErro("Selecione um usuário!");
        processando = false;
        return;
    }

    if (fotosCapturadas >= maxFotos) {
        processando = false;
        return;
    }

    if (!streamAtivo) {
        try {
            btnCapturar.disabled = true;
            btnCapturar.innerText = "Abrindo câmera...";
            await ligarCamera();
        } catch (error) {
            mostrarPopupErro("Não foi possível acessar a câmera.");
            btnCapturar.disabled = false;
            btnCapturar.innerText = "Capturar Foto";
            processando = false;
            return;
        }
    }

    const imagemBase64 = capturarImagem();
    if (!imagemBase64) {
        mostrarPopupErro("Erro ao capturar imagem.");
        processando = false;
        return;
    }

    btnCapturar.disabled = true;
    btnCapturar.innerText = "Salvando...";

    try {
        if (!cadastroIniciado) {
            const resInicio = await fetch("/iniciar_cadastro", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ nome })
            });

            const dataInicio = await resInicio.json();

            if (!resInicio.ok) {
                throw new Error(dataInicio.erro || "Erro ao iniciar cadastro");
            }

            cadastroIniciado = true;
            nomeGlobal = nome;
        }

        const resFoto = await fetch("/adicionar_foto", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                nome: nomeGlobal,
                imagem: imagemBase64
            })
        });

        const dataFoto = await resFoto.json();

        if (!resFoto.ok) {
            throw new Error(dataFoto.erro || "Erro ao salvar foto");
        }

        fotosCapturadas++;
        contador.innerText = `Foto ${fotosCapturadas} de ${maxFotos}`;

        const progresso = (fotosCapturadas / maxFotos) * 100;
        barra.style.width = progresso + "%";

        const cores = ["#e74c3c", "orange", "#f1c40f", "#9acd32", "#2ecc71"];
        barra.style.background = cores[fotosCapturadas - 1];

        if (fotosCapturadas === maxFotos) {
            desligarCamera();

            btnCapturar.disabled = true;
            btnCapturar.innerText = "Processando cadastro...";

            const resFinal = await fetch("/finalizar_cadastro", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ nome: nomeGlobal })
            });

            const dataFinal = await resFinal.json();

            if (!resFinal.ok) {
                let mensagemErro = dataFinal.erro || "Erro ao finalizar cadastro";

                if (dataFinal.erros && dataFinal.erros.length > 0) {
                    mensagemErro += "\n\nDetalhes:\n" + dataFinal.erros.join("\n");
                }

                throw new Error(mensagemErro);
            }

            // ← Sem setTimeout, popup fica aberto até o usuário confirmar
            mostrarPopupSucesso(nomeGlobal, fotosCapturadas);
            return;
        }

    } catch (error) {
        console.error(error);
        mostrarPopupErro(error.message);
    } finally {
        if (fotosCapturadas < maxFotos) {
            btnCapturar.disabled = false;
            btnCapturar.innerText = "Capturar Foto";
        }
        processando = false;
    }
}

// =========================
// MODAL
// =========================
function abrirInstrucoes() {
    modal.classList.add('active');
}

function fecharInstrucoes() {
    modal.classList.remove('active');
}

btnInstrucoes.addEventListener('click', abrirInstrucoes);
btnFecharModal.addEventListener('click', fecharInstrucoes);

window.onclick = function (event) {
    if (event.target === modal) {
        fecharInstrucoes();
    }
}

// =========================
// POPUPS
// =========================
function mostrarPopupSucesso(nome, fotos) {
    document.getElementById("popup-nome").textContent = nome;
    document.getElementById("popup-fotos").textContent = `${fotos} de ${maxFotos}`;
    document.getElementById("popup-ponto").classList.add("ativo");
}

function fecharPopupSucesso() {
    document.getElementById("popup-ponto").classList.remove("ativo");

    // ← Reset e reload só acontecem quando o usuário clica em Confirmar
    fotosCapturadas = 0;
    cadastroIniciado = false;
    nomeGlobal = "";
    contador.innerText = "Foto 0 de 5";
    barra.style.width = "0%";
    document.getElementById("nome").selectedIndex = 0;

    window.location.reload();
}

function mostrarPopupErro(mensagem) {
    document.getElementById("popup-erro-mensagem").textContent = mensagem;
    document.getElementById("popup-erro").classList.add("ativo");
}

function fecharPopupErro() {
    document.getElementById("popup-erro").classList.remove("ativo");
}

document.getElementById("popup-ponto").addEventListener('click', function (event) {
    if (event.target === this) fecharPopupSucesso();
});

document.getElementById("popup-erro").addEventListener('click', function (event) {
    if (event.target === this) fecharPopupErro();
});

// Event Listeners
if (btnCapturar) btnCapturar.addEventListener('click', cadastrar);
if (btnInstrucoes) btnInstrucoes.addEventListener('click', abrirInstrucoes);

const btnVoltar = document.getElementById('btnVoltar');
if (btnVoltar) btnVoltar.addEventListener('click', () => history.back());

const btnFecharSucesso = document.getElementById('btnFecharSucesso');
if (btnFecharSucesso) btnFecharSucesso.addEventListener('click', fecharPopupSucesso);

const btnFecharErro = document.getElementById('btnFecharErro');
if (btnFecharErro) btnFecharErro.addEventListener('click', fecharPopupErro);