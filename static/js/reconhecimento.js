const video = document.getElementById("video");
const btnRegistrar = document.getElementById("btnRegistrar");
const btnInstrucoes = document.getElementById("btnInstrucoes");
const btnFecharModal = document.getElementById("btnFecharModal");
const modal = document.getElementById("modal-instrucoes");

let processando = false;
let dadosPendentes = null; // guarda os dados enquanto aguarda confirmação

// =========================
// CAMERA
// =========================
async function ligarCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }
        });
        video.srcObject = stream;
        await video.play();
        const bg = document.querySelector(".camera-placeholder-bg");
        const status = document.querySelector(".camera-status");
        if (bg) bg.style.display = "none";
        if (status) status.style.display = "none";
    } catch (erro) {
        console.error("Erro câmera:", erro);
        mostrarPopupErro("Não foi possível acessar a câmera.");
    }
}

function desligarCamera() {
    if (video.srcObject) {
        video.srcObject.getTracks().forEach(track => track.stop());
        video.srcObject = null;
    }
    const bg = document.querySelector(".camera-placeholder-bg");
    const status = document.querySelector(".camera-status");
    if (bg) bg.style.display = "block";
    if (status) status.style.display = "block";
}

// =========================
// CAPTURA
// =========================
function capturarImagem() {
    if (!video || video.videoWidth === 0) return null;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    return canvas.toDataURL("image/jpeg", 0.95);
}

// =========================
// RECONHECIMENTO (só identifica)
// =========================
async function registrarPonto() {
    if (processando) return false;
    processando = true;

    const imagem = capturarImagem();
    if (!imagem) { processando = false; return false; }

    try {
        const resposta = await fetch("/reconhecer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ imagem })
        });

        const dados = await resposta.json();
        console.log("RETORNO:", dados);

        if (dados.nome && dados.aguardando_confirmacao) {
            dadosPendentes = dados; // salva para confirmar depois
            desligarCamera();
            mostrarPopupConfirmacao(dados);
            return true;
        } else {
            video.style.border = "4px solid red";
            setTimeout(() => video.style.border = "none", 2000);
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
        if (sucesso) return;
        await new Promise(r => setTimeout(r, 500));
    }
    mostrarPopupErro("Nenhum funcionário identificado!");
}

// =========================
// CONFIRMAR PONTO
// =========================
async function confirmarPonto() {
    if (!dadosPendentes) return;

    fecharPopupConfirmacao();

    try {
        const resposta = await fetch("/confirmar_ponto", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                usuario_id: dadosPendentes.usuario_id,
                nome: dadosPendentes.nome
            })
        });

        const dados = await resposta.json();

        if (dados.registrado) {
            mostrarPopupPonto(dados.nome, dados.data + " às " + dados.horario);
        } else {
            mostrarPopupErro(dados.erro || "Não foi possível registrar o ponto.");
        }

    } catch (erro) {
        console.error("Erro ao confirmar:", erro);
        mostrarPopupErro("Erro ao confirmar o ponto.");
    } finally {
        dadosPendentes = null;
    }
}

function negarPonto() {
    dadosPendentes = null;
    fecharPopupConfirmacao();
    mostrarPopupErro("Ponto não confirmado. Tente novamente.");
}

// =========================
// POPUP CONFIRMAÇÃO
// =========================
function mostrarPopupConfirmacao(dados) {
    document.getElementById("popup-conf-nome").textContent = dados.nome;
    document.getElementById("popup-conf-horario").textContent = dados.data + " às " + dados.horario;
    document.getElementById("popup-confirmacao").classList.add("ativo");
}

function fecharPopupConfirmacao() {
    document.getElementById("popup-confirmacao").classList.remove("ativo");
}

// =========================
// POPUP SUCESSO
// =========================
function mostrarPopupPonto(nome, horario) {
    document.getElementById("popup-nome").textContent = nome;
    document.getElementById("popup-horario").textContent = horario;
    document.getElementById("popup-ponto").classList.add("ativo");
}

function fecharPopupPonto() {
    document.getElementById("popup-ponto").classList.remove("ativo");
    desligarCamera();
    btnRegistrar.disabled = false;
    btnRegistrar.innerText = "Bater Ponto";
}

// =========================
// POPUP ERRO
// =========================
function mostrarPopupErro(mensagem) {
    document.getElementById("popup-erro-mensagem").textContent = mensagem;
    document.getElementById("popup-erro").classList.add("ativo");
}

function fecharPopupErro() {
    document.getElementById("popup-erro").classList.remove("ativo");
    desligarCamera();
    btnRegistrar.disabled = false;
    btnRegistrar.innerText = "Bater Ponto";
}

// =========================
// MODAL INSTRUÇÕES
// =========================
if (btnInstrucoes && modal) {
    btnInstrucoes.addEventListener("click", () => modal.classList.add("active"));
}
if (btnFecharModal && modal) {
    btnFecharModal.addEventListener("click", () => modal.classList.remove("active"));
}
window.addEventListener("click", (e) => {
    if (modal && e.target === modal) modal.classList.remove("active");
});

// =========================
// INIT
// =========================
if (btnRegistrar) {
    btnRegistrar.addEventListener("click", async () => {
        if (btnRegistrar.disabled) return;
        btnRegistrar.disabled = true;
        btnRegistrar.innerText = "Abrindo câmera...";
        await ligarCamera();
        btnRegistrar.innerText = "Processando...";
        await registrarComTentativas();
    });
}