// ELEMENTOS
const video = document.getElementById("video");
const btnCapturar = document.getElementById("btnCapturar");
const btnInstrucoes = document.getElementById("btnInstrucoes");
const btnFecharModal = document.getElementById("btnFecharModal");
const modal = document.getElementById("modal-instrucoes");
const contador = document.getElementById("contador");
const barra = document.getElementById("barra");
const btnFinalizar = document.getElementById("btnFinalizar");

const minFotos = 3;
const maxFotos = 5;
let imagensCapturadas = [];
let processando = false;
let streamAtivo = null;
let funcionarioCapturaId = null;
let nomeCaptura = "";

// =========================
// CARREGAR USUÁRIOS
// =========================
async function carregarUsuarios() {
    try {
        const res = await fetch("/listar_usuarios_select");
        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.erro || "Erro ao carregar lista de funcionários.");
        }

        const select = document.getElementById("nome");

        data.forEach((funcionario) => {
            const option = document.createElement("option");
            option.value = funcionario.funcionario_id;
            option.dataset.nome = funcionario.nome;
            option.textContent = funcionario.possui_biometria_ativa
                ? `${funcionario.nome} — biometria ativa (recadastro)`
                : funcionario.nome;
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
    if (!video || video.videoWidth === 0) return Promise.resolve(null);

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);

    return new Promise((resolve) => {
        canvas.toBlob(resolve, "image/jpeg", 0.95);
    });
}

// =========================
// CADASTRO
// =========================
function atualizarProgresso() {
    const total = imagensCapturadas.length;
    contador.innerText = `Foto ${total} de ${maxFotos}`;
    barra.style.width = `${(total / maxFotos) * 100}%`;
    barra.style.background = total >= minFotos ? "#2ecc71" : "#f1c40f";
    btnFinalizar.disabled = total < minFotos || processando;
    btnCapturar.disabled = total >= maxFotos || processando;
    btnCapturar.innerText = total >= maxFotos ? "Limite de fotos atingido" : "Capturar Foto";
}

async function cadastrar() {
    if (processando) return;
    processando = true;

    const select = document.getElementById("nome");
    const funcionarioId = select.value;
    const selectedOption = select.options[select.selectedIndex];
    const nome = selectedOption?.dataset.nome || "";

    if (!funcionarioId || !nome) {
        mostrarPopupErro("Selecione um usuário!");
        processando = false;
        return;
    }

    if (imagensCapturadas.length >= maxFotos) {
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

    const imagem = await capturarImagem();
    if (!imagem) {
        mostrarPopupErro("Erro ao capturar imagem.");
        processando = false;
        return;
    }

    if (!funcionarioCapturaId) {
        funcionarioCapturaId = funcionarioId;
        nomeCaptura = nome;
        select.disabled = true;
    }

    btnCapturar.disabled = true;
    btnCapturar.innerText = "Capturando...";

    try {
        imagensCapturadas.push(imagem);
        atualizarProgresso();
    } catch (error) {
        console.error(error);
        mostrarPopupErro("Não foi possível manter a imagem capturada.");
    } finally {
        processando = false;
        atualizarProgresso();
    }
}

async function finalizarCadastro() {
    if (processando) return;
    if (imagensCapturadas.length < minFotos || imagensCapturadas.length > maxFotos) {
        mostrarPopupErro("Capture entre 3 e 5 fotos antes de finalizar.");
        return;
    }

    processando = true;
    btnCapturar.disabled = true;
    btnFinalizar.disabled = true;
    btnFinalizar.innerText = "Processando cadastro...";

    try {
        const formData = new FormData();
        imagensCapturadas.forEach((imagem, index) => {
            formData.append("imagem", imagem, `captura-${index + 1}.jpg`);
        });

        const resposta = await fetch(
            `/api/admin/funcionarios/${encodeURIComponent(funcionarioCapturaId)}/biometria`,
            {
                method: "POST",
                body: formData
            }
        );
        const data = await resposta.json();

        if (!resposta.ok) {
            throw new Error(data.erro || "Erro ao cadastrar biometria.");
        }

        const totalEnviado = imagensCapturadas.length;
        desligarCamera();
        imagensCapturadas = [];
        mostrarPopupSucesso(nomeCaptura, totalEnviado);
    } catch (error) {
        console.error(error);
        mostrarPopupErro(error.message);
    } finally {
        processando = false;
        btnFinalizar.innerText = "Finalizar cadastro";
        atualizarProgresso();
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
    imagensCapturadas = [];
    funcionarioCapturaId = null;
    nomeCaptura = "";
    contador.innerText = "Foto 0 de 5";
    barra.style.width = "0%";
    document.getElementById("nome").disabled = false;
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
if (btnFinalizar) btnFinalizar.addEventListener('click', finalizarCadastro);
if (btnInstrucoes) btnInstrucoes.addEventListener('click', abrirInstrucoes);

const btnVoltar = document.getElementById('btnVoltar');
if (btnVoltar) btnVoltar.addEventListener('click', () => history.back());

const btnFecharSucesso = document.getElementById('btnFecharSucesso');
if (btnFecharSucesso) btnFecharSucesso.addEventListener('click', fecharPopupSucesso);

const btnFecharErro = document.getElementById('btnFecharErro');
if (btnFecharErro) btnFecharErro.addEventListener('click', fecharPopupErro);
