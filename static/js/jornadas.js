(() => {
  "use strict";

  const state = {
    turnos: [],
    funcionarios: [],
    turnoEmEdicao: null,
    turnoOriginal: null,
  };

  const diasDaSemana = [
    "Domingo",
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
  ];

  const elementos = {
    mensagem: document.getElementById("mensagem"),
    tabelaTurnos: document.getElementById("tabelaTurnos"),
    editorTurno: document.getElementById("editorTurno"),
    tituloEditor: document.getElementById("tituloEditor"),
    formTurno: document.getElementById("formTurno"),
    nomeTurno: document.getElementById("nomeTurno"),
    timezoneTurno: document.getElementById("timezoneTurno"),
    statusTurno: document.getElementById("statusTurno"),
    listaPeriodos: document.getElementById("listaPeriodos"),
    modeloPeriodo: document.getElementById("modeloPeriodo"),
    funcionario: document.getElementById("funcionario"),
    turnoAtribuicao: document.getElementById("turnoAtribuicao"),
    formAtribuicao: document.getElementById("formAtribuicao"),
    vigenciaInicio: document.getElementById("vigenciaInicio"),
    vigenciaFim: document.getElementById("vigenciaFim"),
    dataConsulta: document.getElementById("dataConsulta"),
    jornadaAtual: document.getElementById("jornadaAtual"),
    tabelaHistorico: document.getElementById("tabelaHistorico"),
  };

  function hojeLocal() {
    const agora = new Date();
    const ano = agora.getFullYear();
    const mes = String(agora.getMonth() + 1).padStart(2, "0");
    const dia = String(agora.getDate()).padStart(2, "0");
    return `${ano}-${mes}-${dia}`;
  }

  function mensagemPadrao(status) {
    const mensagens = {
      400: "Confira os dados informados.",
      401: "Sua sessão expirou. Entre novamente.",
      403: "Você não possui permissão para esta ação.",
      404: "O registro solicitado não foi encontrado.",
      409: "A operação conflita com um registro existente.",
      410: "Esta funcionalidade não está mais disponível.",
      500: "Não foi possível concluir a operação. Tente novamente.",
    };
    return mensagens[status] || "Não foi possível concluir a operação.";
  }

  async function apiRequest(url, options = {}) {
    const config = {
      credentials: "same-origin",
      ...options,
      headers: { ...(options.headers || {}) },
    };
    if (config.body && !config.headers["Content-Type"]) {
      config.headers["Content-Type"] = "application/json";
    }

    let response;
    try {
      response = await fetch(url, config);
    } catch (_error) {
      throw new Error("Não foi possível conectar ao servidor.");
    }

    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }

    if (!response.ok) {
      const safeMessage =
        payload && (payload.erro || payload.mensagem)
          ? String(payload.erro || payload.mensagem)
          : mensagemPadrao(response.status);
      const error = new Error(safeMessage);
      error.status = response.status;
      if (response.status === 401) {
        window.setTimeout(() => {
          window.top.location.href = "/login-page";
        }, 900);
      }
      throw error;
    }

    return payload;
  }

  function exibirMensagem(texto, tipo = "erro") {
    elementos.mensagem.textContent = texto;
    elementos.mensagem.className = `mensagem ${tipo}`;
    elementos.mensagem.hidden = false;
    elementos.mensagem.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function limparMensagem() {
    elementos.mensagem.hidden = true;
    elementos.mensagem.textContent = "";
    elementos.mensagem.className = "mensagem";
  }

  function definirCarregamento(botao, carregando, textoCarregando) {
    if (!botao) return;
    if (carregando) {
      botao.dataset.textoOriginal = botao.textContent;
      botao.textContent = textoCarregando;
      botao.disabled = true;
    } else {
      botao.textContent = botao.dataset.textoOriginal || botao.textContent;
      botao.disabled = false;
    }
  }

  function criarCelula(texto, classe = "") {
    const celula = document.createElement("td");
    celula.textContent = texto;
    if (classe) celula.className = classe;
    return celula;
  }

  function linhaVazia(colunas, texto) {
    const linha = document.createElement("tr");
    const celula = criarCelula(texto, "empty-state");
    celula.colSpan = colunas;
    linha.appendChild(celula);
    return linha;
  }

  function formatarData(valor) {
    if (!valor) return "Sem término";
    const partes = valor.split("-");
    return partes.length === 3 ? `${partes[2]}/${partes[1]}/${partes[0]}` : valor;
  }

  function renderizarTurnos() {
    elementos.tabelaTurnos.replaceChildren();
    if (!state.turnos.length) {
      elementos.tabelaTurnos.appendChild(linhaVazia(5, "Nenhum turno cadastrado."));
    } else {
      state.turnos.forEach((turno) => {
        const linha = document.createElement("tr");
        linha.appendChild(criarCelula(turno.nome));

        const statusCell = document.createElement("td");
        const status = document.createElement("span");
        status.className = `status-chip ${turno.status}`;
        status.textContent = turno.status;
        statusCell.appendChild(status);
        linha.appendChild(statusCell);

        linha.appendChild(criarCelula(turno.timezone));
        linha.appendChild(criarCelula(String(turno.periodos.length)));

        const acoes = document.createElement("td");
        const editar = document.createElement("button");
        editar.type = "button";
        editar.className = "btn-acao";
        editar.textContent = "Editar";
        editar.addEventListener("click", () => abrirEditor(turno));
        acoes.appendChild(editar);
        linha.appendChild(acoes);
        elementos.tabelaTurnos.appendChild(linha);
      });
    }

    const selecionado = elementos.turnoAtribuicao.value;
    elementos.turnoAtribuicao.replaceChildren(new Option("Selecione um turno", ""));
    state.turnos
      .filter((turno) => turno.status === "ativo")
      .forEach((turno) => {
        elementos.turnoAtribuicao.add(new Option(turno.nome, turno.id));
      });
    if ([...elementos.turnoAtribuicao.options].some((item) => item.value === selecionado)) {
      elementos.turnoAtribuicao.value = selecionado;
    }
  }

  function renderizarFuncionarios() {
    elementos.funcionario.replaceChildren(new Option("Selecione um funcionário", ""));
    state.funcionarios
      .filter((funcionario) => funcionario.status === "ativo")
      .forEach((funcionario) => {
        const complemento = funcionario.matricula ? ` — ${funcionario.matricula}` : "";
        elementos.funcionario.add(
          new Option(`${funcionario.nome}${complemento}`, funcionario.funcionario_id)
        );
      });
  }

  async function carregarTurnos() {
    const payload = await apiRequest("/api/admin/turnos");
    state.turnos = Array.isArray(payload.turnos) ? payload.turnos : [];
    renderizarTurnos();
  }

  async function carregarFuncionarios() {
    const payload = await apiRequest("/listarUsuarios");
    state.funcionarios = Array.isArray(payload) ? payload : [];
    renderizarFuncionarios();
  }

  function atualizarOrdemVisual() {
    [...elementos.listaPeriodos.children].forEach((item, index, itens) => {
      item.querySelector(".periodo-ordem").textContent = String(index + 1);
      item.querySelector(".subir-periodo").disabled = index === 0;
      item.querySelector(".descer-periodo").disabled = index === itens.length - 1;
    });
  }

  function adicionarPeriodo(periodo = {}) {
    if (elementos.listaPeriodos.children.length >= 50) {
      exibirMensagem("O limite da interface é de 50 períodos por turno.");
      return;
    }
    const fragmento = elementos.modeloPeriodo.content.cloneNode(true);
    const item = fragmento.querySelector(".periodo-item");
    item.querySelector(".periodo-dia").value = String(periodo.dia_semana ?? 1);
    item.querySelector(".periodo-inicio").value = periodo.inicio || "08:00";
    item.querySelector(".periodo-fim").value = periodo.fim || "12:00";
    item.querySelector(".periodo-offset").checked = Number(periodo.fim_dia_offset) === 1;

    item.querySelector(".subir-periodo").addEventListener("click", () => {
      const anterior = item.previousElementSibling;
      if (anterior) elementos.listaPeriodos.insertBefore(item, anterior);
      atualizarOrdemVisual();
    });
    item.querySelector(".descer-periodo").addEventListener("click", () => {
      const proximo = item.nextElementSibling;
      if (proximo) elementos.listaPeriodos.insertBefore(proximo, item);
      atualizarOrdemVisual();
    });
    item.querySelector(".remover-periodo").addEventListener("click", () => {
      if (elementos.listaPeriodos.children.length === 1) {
        exibirMensagem("O turno deve possuir ao menos um período.");
        return;
      }
      item.remove();
      atualizarOrdemVisual();
    });

    elementos.listaPeriodos.appendChild(fragmento);
    atualizarOrdemVisual();
  }

  function abrirEditor(turno = null) {
    limparMensagem();
    state.turnoEmEdicao = turno ? turno.id : null;
    state.turnoOriginal = turno;
    elementos.tituloEditor.textContent = turno ? "Editar turno" : "Novo turno";
    elementos.nomeTurno.value = turno ? turno.nome : "";
    elementos.timezoneTurno.value = turno ? turno.timezone : "America/Sao_Paulo";
    elementos.statusTurno.value = turno ? turno.status : "ativo";
    elementos.listaPeriodos.replaceChildren();
    const periodos = turno && turno.periodos.length ? turno.periodos : [{}];
    periodos.forEach(adicionarPeriodo);
    elementos.editorTurno.hidden = false;
    elementos.editorTurno.scrollIntoView({ behavior: "smooth", block: "start" });
    elementos.nomeTurno.focus({ preventScroll: true });
  }

  function fecharEditor() {
    state.turnoEmEdicao = null;
    state.turnoOriginal = null;
    elementos.formTurno.reset();
    elementos.listaPeriodos.replaceChildren();
    elementos.editorTurno.hidden = true;
  }

  function coletarPeriodos() {
    const ordensPorDia = new Map();
    return [...elementos.listaPeriodos.querySelectorAll(".periodo-item")].map((item) => {
      const dia = Number(item.querySelector(".periodo-dia").value);
      const ordem = (ordensPorDia.get(dia) || 0) + 1;
      ordensPorDia.set(dia, ordem);
      return {
        dia_semana: dia,
        ordem,
        inicio: item.querySelector(".periodo-inicio").value,
        fim: item.querySelector(".periodo-fim").value,
        fim_dia_offset: item.querySelector(".periodo-offset").checked ? 1 : 0,
      };
    });
  }

  function periodosIguais(primeiros, segundos) {
    const normalizar = (periodos) =>
      periodos.map((periodo) => ({
        dia_semana: Number(periodo.dia_semana),
        ordem: Number(periodo.ordem),
        inicio: periodo.inicio,
        fim: periodo.fim,
        fim_dia_offset: Number(periodo.fim_dia_offset),
      }));
    return JSON.stringify(normalizar(primeiros)) === JSON.stringify(normalizar(segundos));
  }

  async function salvarTurno(event) {
    event.preventDefault();
    limparMensagem();
    const botao = document.getElementById("salvarTurno");
    definirCarregamento(botao, true, "Salvando...");
    try {
      const periodos = coletarPeriodos();
      const dados = {
        nome: elementos.nomeTurno.value.trim(),
        timezone: elementos.timezoneTurno.value.trim(),
        status: elementos.statusTurno.value,
      };
      const editando = Boolean(state.turnoEmEdicao);
      if (
        !editando ||
        !state.turnoOriginal ||
        !periodosIguais(periodos, state.turnoOriginal.periodos)
      ) {
        dados.periodos = periodos;
      }
      const url = editando
        ? `/api/admin/turnos/${encodeURIComponent(state.turnoEmEdicao)}`
        : "/api/admin/turnos";
      await apiRequest(url, {
        method: editando ? "PUT" : "POST",
        body: JSON.stringify(dados),
      });
      fecharEditor();
      await carregarTurnos();
      exibirMensagem(editando ? "Turno atualizado com sucesso." : "Turno criado com sucesso.", "sucesso");
    } catch (error) {
      exibirMensagem(error.message);
    } finally {
      definirCarregamento(botao, false);
    }
  }

  function statusVigencia(vigencia) {
    const hoje = hojeLocal();
    if (vigencia.inicio > hoje) return ["Futura", "futura"];
    if (vigencia.fim && vigencia.fim < hoje) return ["Encerrada", "encerrada"];
    return ["Atual", "atual"];
  }

  async function carregarHistorico(funcionarioId) {
    elementos.tabelaHistorico.replaceChildren(linhaVazia(4, "Carregando histórico..."));
    try {
      const payload = await apiRequest(
        `/api/admin/funcionarios/${encodeURIComponent(funcionarioId)}/turnos`
      );
      elementos.tabelaHistorico.replaceChildren();
      const historico = Array.isArray(payload.historico) ? payload.historico : [];
      if (!historico.length) {
        elementos.tabelaHistorico.appendChild(linhaVazia(4, "Nenhuma atribuição encontrada."));
        return;
      }
      historico.forEach((atribuicao) => {
        const linha = document.createElement("tr");
        linha.appendChild(criarCelula(atribuicao.turno.nome));
        linha.appendChild(criarCelula(formatarData(atribuicao.vigencia.inicio)));
        linha.appendChild(criarCelula(formatarData(atribuicao.vigencia.fim)));
        const [rotulo, classe] = statusVigencia(atribuicao.vigencia);
        const celula = document.createElement("td");
        const chip = document.createElement("span");
        chip.className = `vigencia-chip ${classe}`;
        chip.textContent = rotulo;
        celula.appendChild(chip);
        linha.appendChild(celula);
        elementos.tabelaHistorico.appendChild(linha);
      });
    } catch (error) {
      elementos.tabelaHistorico.replaceChildren(linhaVazia(4, "Não foi possível carregar o histórico."));
      exibirMensagem(error.message);
    }
  }

  function renderizarJornada(jornada, data) {
    elementos.jornadaAtual.replaceChildren();
    if (!jornada) {
      elementos.jornadaAtual.className = "empty-state";
      elementos.jornadaAtual.textContent = `Nenhuma jornada atribuída em ${formatarData(data)}.`;
      return;
    }

    elementos.jornadaAtual.className = "";
    const resumo = document.createElement("div");
    resumo.className = "jornada-resumo";
    [
      ["Turno", jornada.turno.nome],
      ["Timezone", jornada.turno.timezone],
      ["Início", formatarData(jornada.vigencia.inicio)],
      ["Fim", formatarData(jornada.vigencia.fim)],
    ].forEach(([rotulo, valor]) => {
      const item = document.createElement("div");
      const titulo = document.createElement("strong");
      titulo.textContent = rotulo;
      item.append(titulo, document.createTextNode(valor));
      resumo.appendChild(item);
    });

    const periodos = document.createElement("ul");
    periodos.className = "jornada-periodos";
    jornada.periodos.forEach((periodo) => {
      const item = document.createElement("li");
      const dia = diasDaSemana[Number(periodo.dia_semana)] || "Dia inválido";
      const virada = Number(periodo.fim_dia_offset) === 1 ? " (+1 dia)" : "";
      item.textContent = `${dia} · ${periodo.inicio}–${periodo.fim}${virada}`;
      periodos.appendChild(item);
    });
    elementos.jornadaAtual.append(resumo, periodos);
  }

  async function carregarJornada(funcionarioId) {
    const data = elementos.dataConsulta.value || hojeLocal();
    elementos.jornadaAtual.className = "empty-state";
    elementos.jornadaAtual.textContent = "Carregando jornada...";
    try {
      const payload = await apiRequest(
        `/api/admin/funcionarios/${encodeURIComponent(funcionarioId)}/jornada?data=${encodeURIComponent(data)}`
      );
      renderizarJornada(payload.jornada, payload.data || data);
    } catch (error) {
      elementos.jornadaAtual.textContent = "Não foi possível carregar a jornada.";
      exibirMensagem(error.message);
    }
  }

  async function carregarDadosFuncionario() {
    limparMensagem();
    const funcionarioId = elementos.funcionario.value;
    if (!funcionarioId) {
      elementos.tabelaHistorico.replaceChildren(linhaVazia(4, "Selecione um funcionário."));
      elementos.jornadaAtual.className = "empty-state";
      elementos.jornadaAtual.textContent = "Selecione um funcionário.";
      return;
    }
    await Promise.all([carregarHistorico(funcionarioId), carregarJornada(funcionarioId)]);
  }

  async function atribuirTurno(event) {
    event.preventDefault();
    limparMensagem();
    const botao = document.getElementById("atribuirTurno");
    definirCarregamento(botao, true, "Atribuindo...");
    try {
      const funcionarioId = elementos.funcionario.value;
      const dados = {
        turno_id: elementos.turnoAtribuicao.value,
        vigencia_inicio: elementos.vigenciaInicio.value,
        vigencia_fim: elementos.vigenciaFim.value || null,
      };
      await apiRequest(
        `/api/admin/funcionarios/${encodeURIComponent(funcionarioId)}/turnos`,
        { method: "POST", body: JSON.stringify(dados) }
      );
      elementos.vigenciaFim.value = "";
      await carregarDadosFuncionario();
      exibirMensagem("Turno atribuído com sucesso. O histórico anterior foi preservado.", "sucesso");
    } catch (error) {
      exibirMensagem(error.message);
    } finally {
      definirCarregamento(botao, false);
    }
  }

  async function inicializar() {
    elementos.vigenciaInicio.value = hojeLocal();
    elementos.dataConsulta.value = hojeLocal();
    try {
      await Promise.all([carregarTurnos(), carregarFuncionarios()]);
    } catch (error) {
      exibirMensagem(error.message);
    }
  }

  document.getElementById("novoTurno").addEventListener("click", () => abrirEditor());
  document.getElementById("cancelarEdicao").addEventListener("click", fecharEditor);
  document.getElementById("adicionarPeriodo").addEventListener("click", () => adicionarPeriodo());
  document.getElementById("recarregarTurnos").addEventListener("click", async (event) => {
    const botao = event.currentTarget;
    limparMensagem();
    definirCarregamento(botao, true, "Atualizando...");
    try {
      await carregarTurnos();
    } catch (error) {
      exibirMensagem(error.message);
    } finally {
      definirCarregamento(botao, false);
    }
  });
  document.getElementById("consultarJornada").addEventListener("click", () => {
    if (elementos.funcionario.value) carregarJornada(elementos.funcionario.value);
    else exibirMensagem("Selecione um funcionário para consultar a jornada.");
  });
  elementos.funcionario.addEventListener("change", carregarDadosFuncionario);
  elementos.formTurno.addEventListener("submit", salvarTurno);
  elementos.formAtribuicao.addEventListener("submit", atribuirTurno);

  inicializar();
})();
