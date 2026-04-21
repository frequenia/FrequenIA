console.log("JS CARREGADO");

// ELEMENTOS
const video = document.getElementById("video");
const btnRegistrar = document.getElementById("btnRegistrar");
const btnInstrucoes = document.getElementById("btnInstrucoes");
const btnFecharModal = document.getElementById("btnFecharModal");
const modal = document.getElementById("modal-instrucoes");

let processando = false;

// =========================
// CAMERA
// =========================
function ligarCamera() {
    navigator.mediaDevices.getUserMedia({
        video: {
            width: { ideal: 640 },
            height: { ideal: 480 },
            facingMode: "user"
        }
    })
    .then((stream) => {
        video.srcObject = stream;
        video.play();

const bg = document.querySelector(".camera-placeholder-bg");
const status = document.querySelector(".camera-status");
if (bg) bg.style.display = "none";
if (status) status.style.display = "none";
    })
    .catch((erro) => {
        console.error("Erro câmera:", erro);
        mostrarPopupErro("Não foi possível acessar a câmera.");
    });
}

// =========================
// CAPTURA
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
// RECONHECIMENTO
// =========================
async function registrarPonto() {
    if (processando) return false;
    processando = true;

    const imagem = capturarImagem();
    if (!imagem) {
        processando = false;
        return false;
    }

    try {
        const resposta = await fetch("/reconhecer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ imagem })
        });

        const dados = await resposta.json();
        console.log("RETORNO:", dados);

        const nomeRegistro = document.getElementById("nomeRegistro");
        const dataRegistro = document.getElementById("dataRegistro");
        const horaRegistro = document.getElementById("horaRegistro");

        if (nomeRegistro && dados.nome) {
            nomeRegistro.innerText = "Nome: " + dados.nome;
        }

        if (dataRegistro && dados.data) {
            dataRegistro.innerText = "Data: " + dados.data;
        }

        if (horaRegistro && dados.horario) {
            horaRegistro.innerText = "Hora: " + dados.horario;
        }

        if (dados.nome && dados.data && dados.horario) {
            mostrarPopupPonto(dados.nome, dados.data + " às " + dados.horario);

            video.style.border = "4px solid green";
            setTimeout(() => {
                video.style.border = "none";
            }, 2000);

            return true;
        } else {
            video.style.border = "4px solid red";
            setTimeout(() => {
                video.style.border = "none";
            }, 2000);

            return false;
        }

    } catch (erro) {
        console.error("Erro:", erro);
        mostrarPopupErro("Erro no reconhecimento.");
        return false;
    } finally {
        processando = false;
    }
}

// =========================
// 3 TENTATIVAS
// =========================
async function registrarComTentativas() {
    for (let i = 0; i < 3; i++) {
        console.log("Tentativa:", i + 1);

        const sucesso = await registrarPonto();

        if (sucesso) {
            return;
        }

        await new Promise(r => setTimeout(r, 500));
    }

    mostrarPopupErro("Nenhum funcionário identificado!");
}

// =========================
// MODAL INSTRUÇÕES
// =========================
if (btnInstrucoes && modal) {
    btnInstrucoes.addEventListener("click", () => {
        modal.classList.add("active");
    });
}

if (btnFecharModal && modal) {
    btnFecharModal.addEventListener("click", () => {
        modal.classList.remove("active");
    });
}

window.addEventListener("click", (event) => {
    if (modal && event.target === modal) {
        modal.classList.remove("active");
    }
});

// =========================
// POPUP SUCESSO
// =========================
function mostrarPopupPonto(nome, horario) {
    const nomeEl = document.getElementById("popup-nome");
    const horarioEl = document.getElementById("popup-horario");
    const popup = document.getElementById("popup-ponto");

    if (nomeEl) nomeEl.textContent = nome;
    if (horarioEl) horarioEl.textContent = horario;
    if (popup) popup.classList.add("ativo");
}

function fecharPopupPonto() {
    const popup = document.getElementById("popup-ponto");
    if (popup) popup.classList.remove("ativo");
}

// =========================
// POPUP ERRO
// =========================
function mostrarPopupErro(mensagem) {
    const mensagemEl = document.getElementById("popup-erro-mensagem");
    const popup = document.getElementById("popup-erro");

    if (mensagemEl) mensagemEl.textContent = mensagem;
    if (popup) popup.classList.add("ativo");
}

function fecharPopupErro() {
    const popup = document.getElementById("popup-erro");
    if (popup) popup.classList.remove("ativo");
}

// =========================
// INIT
// =========================
window.addEventListener("load", ligarCamera);

if (btnRegistrar) {
    btnRegistrar.addEventListener("click", registrarComTentativas);
}