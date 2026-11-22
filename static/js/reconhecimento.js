const video = document.getElementById("video");
const matricula = document.getElementById("matricula");
const button = document.getElementById("btnRegistrar");
const retryButton = document.getElementById("btnTentarCamera");
const status = document.getElementById("kiosk-status");
const cameraState = document.getElementById("camera-state");
const feedback = document.getElementById("kiosk-feedback");
const feedbackTitle = document.getElementById("feedback-title");
const feedbackMessage = document.getElementById("feedback-message");
const feedbackHint = document.getElementById("feedback-hint");
const receipt = document.getElementById("feedback-receipt");
const receiptName = document.getElementById("receipt-name");
const receiptTime = document.getElementById("receipt-time");
const receiptType = document.getElementById("receipt-type");
const continueButton = document.getElementById("btnContinuar");
const markingLabels = { entrada: "Entrada", saida_intervalo: "Saída para intervalo", retorno_intervalo: "Retorno do intervalo", saida: "Saída" };

let stream = null;
let processing = false;
let resetTimer = null;
let leavingPage = false;

function clearReceipt() {
  receipt.hidden = true;
  receiptName.textContent = "";
  receiptTime.textContent = "";
  receiptType.textContent = "";
}

function showFeedback({ title, message, hint, confirmation = null }) {
  clearTimeout(resetTimer);
  stopCamera();
  button.disabled = true;
  matricula.value = "";
  clearReceipt();
  const state = confirmation ? "success" : "error";
  feedback.dataset.state = state;
  feedbackTitle.textContent = title;
  feedbackMessage.textContent = message;
  feedbackHint.textContent = hint;
  document.getElementById("feedback-symbol").textContent = confirmation ? "✓" : "!";
  setStatus(message, state);
  if (confirmation) {
    receiptName.textContent = confirmation.name;
    receiptTime.textContent = confirmation.time;
    receiptType.textContent = confirmation.type;
    receipt.hidden = false;
  }
  if (!feedback.open) feedback.showModal();
  continueButton.focus();
  // O quiosque nao retém a identificação do funcionário seguinte.
  if (confirmation) resetTimer = setTimeout(() => feedback.close(), 10000);
}

function errorFeedback(body = {}, httpStatus = 0) {
  if (!body || typeof body !== "object") body = {};
  const known = {
    jornada_nao_configurada: ["Jornada não configurada", "Não há jornada disponível para registrar este ponto.", "Peça ao responsável para conferir sua escala e a vigência da jornada."],
    jornada_concluida: ["Jornada concluída", "Os eventos previstos nesta jornada já foram concluídos.", "Se faltar uma marcação, solicite uma correção ao responsável."],
    folga_programada: ["Dia de folga", "A jornada indica folga para este dia.", "Confirme sua escala com o responsável antes de tentar novamente."],
    marcacao_recente: ["Marcação recente", "Já existe uma marcação registrada recentemente.", "Confira o histórico antes de tentar registrar outro ponto."],
  };
  let details = known[body.codigo];
  if (!details) {
    if (httpStatus === 401) details = ["Terminal não autenticado", "A ativação deste terminal precisa ser conferida.", "Solicite ao administrador a ativação do quiosque."];
    else if (httpStatus === 403) details = ["Registro não autorizado", "O registro não está disponível para esta tentativa.", "Procure o responsável para conferir as permissões e a disponibilidade do reconhecimento."];
    else if (httpStatus === 422) details = ["Imagem não validada", typeof body.erro === "string" ? body.erro : "Não foi possível validar a imagem capturada.", "Mantenha apenas um rosto na câmera, centralize-o e confira a iluminação."];
    else if (httpStatus === 409) details = ["Verificação não concluída", typeof body.erro === "string" ? body.erro : "Não foi possível concluir esta tentativa.", "Confira o enquadramento e tente novamente. Se persistir, procure o responsável para atendimento alternativo."];
    else if (httpStatus === 400) details = ["Confira os dados", typeof body.erro === "string" ? body.erro : "A solicitação não pôde ser validada.", "Confira a matrícula e tente novamente."];
    else if (httpStatus === 503) details = ["Serviço indisponível", "O serviço necessário para esta tentativa está temporariamente indisponível.", "Aguarde e tente novamente. Se persistir, procure o responsável."];
    else if (httpStatus >= 500) details = ["Não foi possível confirmar o registro", "O servidor encontrou uma falha ao concluir a solicitação.", "Confira seu histórico antes de repetir a tentativa e procure o responsável se necessário."];
    else details = ["Falha de conexão", "Não foi possível confirmar a resposta do servidor.", "Verifique sua conexão e confira o histórico antes de repetir a tentativa."];
  }
  return { title: details[0], message: details[1], hint: details[2] };
}

function markingConfirmation(body) {
  if (!body || typeof body !== "object") return null;
  const marking = body.marcacao;
  const name = body.funcionario && body.funcionario.nome;
  if (!marking || marking.estado !== "confirmada" || !markingLabels[marking.tipo] || typeof name !== "string" || !name.trim()) return null;
  if (typeof marking.instante !== "string" || !/(Z|[+-]\d{2}:\d{2})$/.test(marking.instante)) return null;
  const date = new Date(marking.instante);
  if (!Number.isFinite(date.getTime())) return null;
  const options = { dateStyle: "short", timeStyle: "medium", timeZone: (body.jornada && body.jornada.timezone) || "America/Sao_Paulo" };
  let time;
  try { time = new Intl.DateTimeFormat("pt-BR", options).format(date); }
  catch { time = new Intl.DateTimeFormat("pt-BR", { ...options, timeZone: "America/Sao_Paulo" }).format(date); }
  return { name, time, type: markingLabels[marking.tipo] };
}

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
    showFeedback({ title: "Câmera indisponível", message: cameraErrorMessage(error), hint: "Confira a câmera e as permissões do navegador antes de continuar." });
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

async function registerClock() {
  if (processing) return;
  if (!stream) {
    await openCamera();
    return;
  }
  if (!matricula.value.trim()) {
    showFeedback({ title: "Informe sua matrícula", message: "A matrícula é necessária para registrar o ponto.", hint: "Use a matrícula informada pela sua empresa." });
    return;
  }

  processing = true;
  button.disabled = true;
  try {
    setStatus("Verificando presença e registrando ponto…");
    const photo = await captureImage();
    if (!photo) {
      showFeedback({ title: "Imagem não capturada", message: "A câmera ainda não forneceu uma imagem válida.", hint: "Aguarde a câmera ficar pronta antes de tentar novamente." });
      return;
    }

    const formData = new FormData();
    formData.append("matricula", matricula.value.trim());
    formData.append("imagem", photo, "captura.jpg");
    const response = await fetch("/api/quiosque/marcacoes/facial", {
      method: "POST",
      body: formData,
      headers: { "Idempotency-Key": idempotencyKey() },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      showFeedback(errorFeedback(body, response.status));
      return;
    }
    const confirmation = markingConfirmation(body);
    if (!confirmation) {
      showFeedback({ title: "Confira o resultado no histórico", message: "O servidor respondeu, mas a confirmação recebida está incompleta.", hint: "Confira o histórico antes de repetir a marcação." });
      return;
    }
    showFeedback({ title: body.reutilizada ? "Ponto já confirmado" : "Ponto registrado!", message: body.reutilizada ? "Esta marcação já estava registrada. Nenhum novo ponto foi criado." : "Registro confirmado com sucesso.", hint: "Esta confirmação será fechada em 10 segundos.", confirmation });
  } catch (error) {
    showFeedback(errorFeedback());
  } finally {
    processing = false;
  }
}

button.addEventListener("click", registerClock);
retryButton.addEventListener("click", openCamera);
continueButton.addEventListener("click", () => feedback.close());
feedback.addEventListener("close", () => {
  clearTimeout(resetTimer);
  clearReceipt();
  feedbackTitle.textContent = "";
  feedbackMessage.textContent = "";
  feedbackHint.textContent = "";
  if (!leavingPage) openCamera();
});
window.addEventListener("pagehide", () => {
  leavingPage = true;
  clearTimeout(resetTimer);
  clearReceipt();
  feedbackTitle.textContent = feedbackMessage.textContent = feedbackHint.textContent = "";
  if (feedback.open) feedback.close();
});
window.addEventListener("pagehide", stopCamera);
window.addEventListener("beforeunload", stopCamera);

openCamera();
