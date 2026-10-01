const video = document.getElementById("video");
const matricula = document.getElementById("matricula");
const tipo = document.getElementById("tipo");
const button = document.getElementById("btnRegistrar");
const retryButton = document.getElementById("btnTentarCamera");
const status = document.getElementById("kiosk-status");
const cameraState = document.getElementById("camera-state");

let stream = null;
let processing = false;
let resetTimer = null;

function setStatus(message, state = "info") {
  status.textContent = message;
  status.dataset.state = state;
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
  }
  stream = null;
  video.srcObject = null;
  video.classList.remove("camera-video--active");
}

function cameraErrorMessage(error) {
  if (!window.isSecureContext) {
    return "A câmera exige HTTPS. Neste computador, abra o sistema por HTTPS ou use localhost.";
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return "Este navegador não oferece acesso à câmera. Atualize o navegador ou use Chrome, Edge ou Firefox.";
  }

  const messages = {
    NotAllowedError: "A permissão da câmera foi bloqueada. Libere a câmera nas permissões do site e tente novamente.",
    SecurityError: "O navegador bloqueou a câmera por segurança. Verifique a permissão do site.",
    NotFoundError: "Nenhuma câmera foi encontrada neste computador.",
    DevicesNotFoundError: "Nenhuma câmera foi encontrada neste computador.",
    NotReadableError: "A câmera está ocupada por outro aplicativo. Feche-o e tente novamente.",
    TrackStartError: "A câmera está ocupada por outro aplicativo. Feche-o e tente novamente.",
    OverconstrainedError: "A câmera disponível não suporta a configuração necessária.",
  };
  return messages[error && error.name] || "Não foi possível abrir a câmera. Verifique a conexão e a permissão do navegador.";
}

async function openCamera() {
  clearTimeout(resetTimer);
  retryButton.hidden = true;
  button.disabled = true;
  cameraState.textContent = "Abrindo câmera…";
  setStatus("Autorize o uso da câmera quando o navegador solicitar.");

  try {
    if (!window.isSecureContext) {
      throw new DOMException("Contexto inseguro", "SecurityError");
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new DOMException("API de mídia indisponível", "NotSupportedError");
    }

    stopCamera();
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: "user" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    });
    video.srcObject = stream;
    await video.play();
    video.classList.add("camera-video--active");
    cameraState.textContent = "Câmera pronta";
    button.disabled = false;
    setStatus("Câmera pronta. Informe sua matrícula e registre o ponto.", "success");
    matricula.focus();
    return true;
  } catch (error) {
    stopCamera();
    cameraState.textContent = "Câmera indisponível";
    retryButton.hidden = false;
    button.disabled = true;
    setStatus(cameraErrorMessage(error), "error");
    return false;
  }
}

function captureImage() {
  if (!stream || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !video.videoWidth) {
    return Promise.resolve(null);
  }
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext("2d");
  if (!context) return Promise.resolve(null);
  context.drawImage(video, 0, 0);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
}

function idempotencyKey() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function resetAfterAttempt(message, state) {
  stopCamera();
  matricula.value = "";
  tipo.value = "entrada";
  setStatus(message, state);
  resetTimer = setTimeout(openCamera, 2500);
}

async function registerClock() {
  if (processing) return;
  if (!stream) {
    await openCamera();
    return;
  }
  if (!matricula.value.trim()) {
    setStatus("Informe sua matrícula antes de registrar o ponto.", "error");
    matricula.focus();
    return;
  }

  processing = true;
  button.disabled = true;
  try {
    setStatus("Verificando presença e registrando ponto…");
    const photo = await captureImage();
    if (!photo) throw new Error("Não foi possível capturar a imagem da câmera.");

    const formData = new FormData();
    formData.append("matricula", matricula.value.trim());
    formData.append("tipo", tipo.value);
    formData.append("imagem", photo, "captura.jpg");
    const response = await fetch("/api/quiosque/marcacoes/facial", {
      method: "POST",
      body: formData,
      headers: { "Idempotency-Key": idempotencyKey() },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      await resetAfterAttempt(body.erro || "Não foi possível concluir a tentativa.", "error");
      return;
    }
    await resetAfterAttempt("Ponto registrado com sucesso.", "success");
  } catch (error) {
    await resetAfterAttempt(error.message || "Não foi possível concluir a tentativa.", "error");
  } finally {
    processing = false;
  }
}

button.addEventListener("click", registerClock);
retryButton.addEventListener("click", openCamera);
window.addEventListener("pagehide", stopCamera);
window.addEventListener("beforeunload", stopCamera);

openCamera();
