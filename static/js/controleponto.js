const TIMEZONE_LOCAL = "America/Sao_Paulo";
let jornadaPadrao = null;
let diasCarregados = [];
let paginaAtual = 1;
let filtrosAplicados = { status: "", cor: "", horario: "", ordem: "desc", itensPagina: 10 };

function sincronizarSelect(select) {
    const wrapper = select.closest(".custom-select");
    if (!wrapper) return;
    const menu = wrapper.querySelector('[role="listbox"]');
    const trigger = wrapper.querySelector(".select-trigger");
    menu.replaceChildren();
    Array.from(select.options).forEach((option) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "select-option";
        item.dataset.value = option.value;
        item.setAttribute("role", "option");
        item.textContent = option.textContent;
        item.addEventListener("click", () => {
            select.value = option.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
            atualizarSelectVisual(select);
            wrapper.classList.remove("open");
            if (trigger.tagName === "INPUT") {
                trigger.value = option.value ? option.textContent : "";
                trigger.setAttribute("aria-expanded", "false");
            }
            trigger.focus();
            wrapper.classList.remove("open");
        });
        menu.appendChild(item);
    });
    atualizarSelectVisual(select);
    if (trigger) trigger.disabled = !select.options.length;
}

function atualizarSelectVisual(select) {
    const wrapper = select.closest(".custom-select");
    if (!wrapper) return;
    const selected = select.options[select.selectedIndex];
    const trigger = wrapper.querySelector(".select-trigger");
    if (selected && trigger) {
        if (trigger.tagName === "INPUT") trigger.value = selected.value ? selected.textContent : "";
        else trigger.querySelector(".select-label").textContent = selected.textContent;
    }
    wrapper.querySelectorAll(".select-option").forEach((item) => {
        item.classList.toggle("selected", item.dataset.value === select.value);
        item.setAttribute("aria-selected", String(item.dataset.value === select.value));
    });
}

function ativarSelectCustomizado(select) {
    if (select.closest(".custom-select")) return;
    const wrapper = document.createElement("div");
    wrapper.className = "custom-select";
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);
    const pesquisavel = select.id === "filtroUsuario";
    const trigger = document.createElement(pesquisavel ? "input" : "button");
    trigger.type = pesquisavel ? "search" : "button";
    trigger.className = "select-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    if (pesquisavel) {
        trigger.placeholder = "Buscar por nome ou matrícula";
        trigger.setAttribute("aria-label", trigger.placeholder);
        trigger.setAttribute("role", "combobox");
        trigger.setAttribute("aria-autocomplete", "list");
        trigger.setAttribute("aria-expanded", "false");
        trigger.autocomplete = "off";
    } else {
        trigger.innerHTML = '<span class="select-label"></span><span class="select-chevron" aria-hidden="true"></span>';
    }
    const menu = document.createElement("div");
    menu.className = "select-menu";
    menu.setAttribute("role", "listbox");
    if (pesquisavel) {
        const normalizar = texto => texto.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
        trigger.addEventListener("input", () => {
            const termo = normalizar(trigger.value);
            menu.querySelectorAll(".select-option").forEach(opcao => {
                opcao.hidden = Boolean(termo) && !normalizar(opcao.textContent).includes(termo);
            });
            wrapper.classList.add("open");
            trigger.setAttribute("aria-expanded", "true");
        });
        trigger.addEventListener("focus", () => {
            menu.querySelectorAll(".select-option").forEach(opcao => { opcao.hidden = false; });
            wrapper.classList.add("open");
            trigger.setAttribute("aria-expanded", "true");
        });
        wrapper.addEventListener("focusout", () => {
            setTimeout(() => {
                if (wrapper.contains(document.activeElement)) return;
                wrapper.classList.remove("open");
                trigger.setAttribute("aria-expanded", "false");
                atualizarSelectVisual(select);
            }, 0);
        });
        trigger.addEventListener("keydown", event => {
            if (event.key === "Escape") {
                wrapper.classList.remove("open");
                trigger.setAttribute("aria-expanded", "false");
                trigger.blur();
            } else if (event.key === "ArrowDown") {
                event.preventDefault();
                menu.querySelector(".select-option:not([hidden])")?.focus();
            }
        });
    }
    wrapper.insertBefore(trigger, select);
    wrapper.appendChild(menu);
    select.classList.add("native-select");
    if (!pesquisavel) trigger.addEventListener("click", () => {
        document.querySelectorAll(".custom-select.open").forEach((item) => { if (item !== wrapper) item.classList.remove("open"); });
        wrapper.classList.toggle("open");
    });
    select.addEventListener("change", () => atualizarSelectVisual(select));
    sincronizarSelect(select);
}

function ativarListasSuspensas() {
    document.querySelectorAll("select").forEach(ativarSelectCustomizado);
    document.addEventListener("click", (event) => {
        if (!event.target.closest(".custom-select")) document.querySelectorAll(".custom-select.open").forEach((item) => item.classList.remove("open"));
    });
}

function criarCelulaHora(valor, indicador = "", diferencaMinutos = null) {
    if (!valor || valor === "--:--") return '<div class="hora">--:--</div>';
    const diferenca = Number.isFinite(Number(diferencaMinutos)) ? Math.abs(Number(diferencaMinutos)) : null;
    const classe = diferenca === null || indicador === "no_horario" || diferenca <= 5 ? "ok" : (diferenca <= 10 ? "alerta" : "relevante");
    return `<div class="hora ${classe}">${valor}</div>`;
}

function formatarDataBR(dataIso) {
    const [ano, mes, dia] = dataIso.split("-");
    return `${dia}/${mes}/${ano}`;
}

function converterDataParaIso(dataBr) {
    if (!dataBr) return "";
    const partes = dataBr.split("/");
    if (partes.length !== 3) return "";
    return `${partes[2]}-${partes[1]}-${partes[0]}`;
}

function hojeEmSaoPaulo() {
    const partes = new Intl.DateTimeFormat("pt-BR", {
        timeZone: TIMEZONE_LOCAL,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).formatToParts(new Date());
    const valor = Object.fromEntries(partes.map((parte) => [parte.type, parte.value]));
    return `${valor.year}-${valor.month}-${valor.day}`;
}

function preencherPeriodoPadrao() {
    const fimIso = hojeEmSaoPaulo();
    const fim = new Date(`${fimIso}T00:00:00Z`);
    const inicio = new Date(fim);
    inicio.setUTCDate(inicio.getUTCDate() - 9);
    const inicioIso = inicio.toISOString().slice(0, 10);
    const campoInicio = document.getElementById("dataInicio");
    const campoFim = document.getElementById("dataFim");
    if (!campoInicio.value) campoInicio.value = formatarDataBR(inicioIso);
    if (!campoFim.value) campoFim.value = formatarDataBR(fimIso);
}

function mensagemPadrao(status) {
    const mensagens = {
        400: "Confira os filtros informados.",
        401: "Sua sessão expirou. Entre novamente.",
        403: "Você não possui permissão para acessar o Controle de Ponto.",
        404: "Funcionário ou registros não encontrados.",
        500: "Não foi possível concluir a operação.",
    };
    return mensagens[status] || "Não foi possível concluir a operação.";
}

async function apiJson(url) {
    let resposta;
    try {
        resposta = await fetch(url, { credentials: "same-origin" });
    } catch (_erro) {
        throw new Error("Não foi possível conectar ao servidor.");
    }
    let payload = null;
    try {
        payload = await resposta.json();
    } catch (_erro) {
        payload = null;
    }
    if (!resposta.ok) {
        if (resposta.status === 401) {
            window.setTimeout(() => { window.top.location.href = "/login-page"; }, 700);
        }
        throw new Error(payload?.erro || mensagemPadrao(resposta.status));
    }
    return payload;
}

function limparJornada(mensagem = "") {
    jornadaPadrao = null;
    ["hora-entrada", "hora-saida-intervalo", "hora-volta-intervalo", "hora-saida"]
        .forEach((id) => { document.getElementById(id).textContent = "--:--"; });
    ["previsto-entrada", "previsto-saida-intervalo", "previsto-volta-intervalo", "previsto-saida"]
        .forEach((id) => { document.getElementById(id).textContent = "--:--"; });
    ["entrada", "saida-intervalo", "volta-intervalo", "saida"].forEach((tipo) => {
        const state = document.getElementById(`estado-${tipo}`);
        const card = state?.closest(".jornada-card-item");
        const delta = document.getElementById(`delta-${tipo}`);
        if (card) card.classList.remove("status-registered", "status-warning", "status-pending");
        if (card) card.classList.add("status-pending");
        if (state) { state.className = "jornada-state pending"; state.innerHTML = '<span class="dot"></span>Aguardando'; }
        if (delta) delta.textContent = "Aguardando";
    });
    const card = document.querySelector(".card.jornada");
    if (card) card.title = mensagem;
}

function exibirHoraPrevista(id, periodo, campo) {
    const elemento = document.getElementById(id);
    if (!periodo) {
        elemento.textContent = "--:--";
        return;
    }
    const valor = periodo[campo];
    const cruzaDia = campo === "fim" && Number(periodo.fim_dia_offset) === 1;
    elemento.textContent = cruzaDia ? `${valor} (+1 dia)` : valor;
}

function aplicarJornada(jornada, dataReferencia) {
    limparJornada();
    if (!jornada || !Array.isArray(jornada.periodos)) return;

    const diaSemana = new Date(`${dataReferencia}T00:00:00Z`).getUTCDay();
    const periodos = jornada.periodos
        .filter((periodo) => Number(periodo.dia_semana) === diaSemana)
        .sort((a, b) => Number(a.ordem) - Number(b.ordem));
    if (!periodos.length) return;

    const primeiro = periodos[0];
    const ultimo = periodos[periodos.length - 1];
    if (periodos.length === 1) {
        jornadaPadrao = {
            entrada: primeiro.inicio,
            saida_intervalo: null,
            retorno_intervalo: null,
            saida: primeiro.fim,
        };
        exibirHoraPrevista("previsto-entrada", primeiro, "inicio");
        exibirHoraPrevista("previsto-saida", primeiro, "fim");
        return;
    }

    if (periodos.length === 2) {
        jornadaPadrao = {
            entrada: primeiro.inicio,
            saida_intervalo: primeiro.fim,
            retorno_intervalo: ultimo.inicio,
            saida: ultimo.fim,
        };
        exibirHoraPrevista("previsto-entrada", primeiro, "inicio");
        exibirHoraPrevista("previsto-saida-intervalo", primeiro, "fim");
        exibirHoraPrevista("previsto-volta-intervalo", ultimo, "inicio");
        exibirHoraPrevista("previsto-saida", ultimo, "fim");
        return;
    }

    // A tela possui apenas um par de intervalo. Para três ou mais períodos,
    // exibe somente os limites externos e não inventa qual intervalo comparar.
    jornadaPadrao = {
        entrada: primeiro.inicio,
        saida_intervalo: null,
        retorno_intervalo: null,
        saida: ultimo.fim,
    };
    exibirHoraPrevista("previsto-entrada", primeiro, "inicio");
    exibirHoraPrevista("previsto-saida", ultimo, "fim");
    const card = document.querySelector(".card.jornada");
    if (card) {
        card.title = `A jornada possui ${periodos.length} períodos; os intervalos adicionais não cabem neste resumo.`;
    }
}

function dataReferenciaJornada() {
    return converterDataParaIso(document.getElementById("dataInicio").value) || hojeEmSaoPaulo();
}

async function carregarJornada(funcionarioId) {
    limparJornada();
    if (!funcionarioId) return;
    const data = hojeEmSaoPaulo();
    const url = `/api/admin/funcionarios/${encodeURIComponent(funcionarioId)}/jornada?data=${encodeURIComponent(data)}`;
    const payload = await apiJson(url);
    aplicarJornada(payload.jornada, payload.data || data);
}

async function carregarFuncionarios() {
    const select = document.getElementById("filtroUsuario");
    const funcionarios = await apiJson("/api/gestao/funcionarios");
    select.replaceChildren(new Option("Selecione", ""));
    funcionarios.forEach((item) => {
        const rotulo = item.matricula ? `${item.nome} - ${item.matricula}` : item.nome;
        select.add(new Option(rotulo, item.funcionario_id));
    });
    sincronizarSelect(select);
}

function parametrosSelecionados(incluirFormato = false) {
    const funcionarioId = document.getElementById("filtroUsuario").value;
    if (!funcionarioId) throw new Error("Selecione um funcionário.");
    const params = new URLSearchParams({ funcionario_id: funcionarioId });
    const inicio = converterDataParaIso(document.getElementById("dataInicio").value);
    const fim = converterDataParaIso(document.getElementById("dataFim").value);
    if (inicio) params.set("inicio", inicio);
    if (fim) params.set("fim", fim);
    if (incluirFormato) {
        const formato = document.getElementById("exportFormat").value;
        if (!formato) throw new Error("Selecione um formato para exportação.");
        params.set("formato", formato);
    }
    return params;
}

function mostrarMensagemTabela(texto) {
    const tbody = document.getElementById("tabela-pontos-body");
    const linha = document.createElement("tr");
    const celula = document.createElement("td");
    celula.colSpan = 7;
    celula.style.textAlign = "center";
    celula.textContent = texto;
    linha.appendChild(celula);
    tbody.replaceChildren(linha);
}

function minutosDoDia(item) {
    const match = String(item?.duracao_descritiva || "").match(/^(\d+)h(\d{2})$/);
    return match ? Number(match[1]) * 60 + Number(match[2]) : 0;
}

function selecionarDiaRelatorio(dataIso, minutos) {
    const hoje = hojeEmSaoPaulo();
    const nomes = ["Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"];
    const diaSemana = new Date(`${dataIso}T12:00:00Z`).getUTCDay();
    const valor = `${Math.floor(minutos / 60)}h${String(minutos % 60).padStart(2, "0")}`;
    const value = document.getElementById("rail-hours-value");
    const caption = document.getElementById("rail-hours-caption");
    if (value) value.textContent = valor;
    if (caption) caption.textContent = `${dataIso === hoje ? "Hoje" : nomes[diaSemana]} · ${formatarDataBR(dataIso)}${minutos ? "" : " · Sem registros"}`;
    document.querySelectorAll("[data-week-day]").forEach((item) => {
        item.classList.toggle("selected", Number(item.dataset.weekDay) === diaSemana);
    });
}

function atualizarGraficoSemanal(dias) {
    const hojeIso = hojeEmSaoPaulo();
    const hoje = new Date(`${hojeIso}T12:00:00Z`);
    const inicio = new Date(hoje);
    inicio.setUTCDate(inicio.getUTCDate() - hoje.getUTCDay());
    const dadosSemana = Array.from({ length: 7 }, (_, dia) => {
        const data = new Date(inicio);
        data.setUTCDate(inicio.getUTCDate() + dia);
        const iso = data.toISOString().slice(0, 10);
        const item = dias.find((registro) => registro.data_operacional === iso);
        return { dia, iso, minutos: minutosDoDia(item) };
    });
    const maior = Math.max(...dadosSemana.map((item) => item.minutos), 1);
    document.querySelectorAll(".week-bars [data-week-day]").forEach((bar) => {
        const item = dadosSemana[Number(bar.dataset.weekDay)];
        bar.style.height = `${Math.max(item.minutos ? 24 : 12, Math.round((item.minutos / maior) * 88))}%`;
        bar.classList.toggle("muted", item.minutos === 0);
        bar.title = item.minutos ? `${Math.floor(item.minutos / 60)}h${String(item.minutos % 60).padStart(2, "0")}` : "Sem registros";
        bar.onclick = () => selecionarDiaRelatorio(item.iso, item.minutos);
    });
    document.querySelectorAll(".week-labels [data-week-day]").forEach((label) => {
        const item = dadosSemana[Number(label.dataset.weekDay)];
        label.onclick = () => selecionarDiaRelatorio(item.iso, item.minutos);
    });
    const hojeDia = dadosSemana[hoje.getUTCDay()];
    selecionarDiaRelatorio(hojeDia.iso, hojeDia.minutos);
}

function atualizarResumoLateral(dias) {
    const totalMinutos = dias.reduce((total, item) => {
        const match = String(item.duracao_descritiva || "").match(/^(\d+)h(\d{2})$/);
        return match ? total + (Number(match[1]) * 60) + Number(match[2]) : total;
    }, 0);
    const horas = Math.floor(totalMinutos / 60);
    const minutos = String(totalMinutos % 60).padStart(2, "0");
    const divergencias = dias.reduce((total, item) => (
        total + (item.eventos || []).filter((evento) => evento.efetiva && Math.abs(Number(evento.diferenca_minutos || 0)) > 5).length
    ), 0);
    const pendencias = dias.filter((item) => ["incompleto", "sem_marcacao", "snapshot_ausente"].includes(item.estado_informativo)).length;
    const setText = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    };
    setText("rail-registered-value", totalMinutos ? `${horas}h${minutos}` : "—");
    setText("rail-divergences-value", String(divergencias));
    setText("rail-pending-value", String(pendencias));
    atualizarGraficoSemanal(dias);
}

function atualizarCardsJornada(dias) {
    const referencia = hojeEmSaoPaulo();
    const item = dias.find((dia) => dia.data_operacional === referencia);
    const porTipo = Object.fromEntries((item?.eventos || []).map((evento) => [evento.tipo, evento]));
    const mapa = { entrada: "entrada", saida_intervalo: "saida-intervalo", retorno_intervalo: "volta-intervalo", saida: "saida" };
    Object.entries(mapa).forEach(([tipo, sufixo]) => {
        const evento = porTipo[tipo];
        const actual = document.getElementById(`hora-${sufixo}`);
        const delta = document.getElementById(`delta-${sufixo}`);
        const state = document.getElementById(`estado-${sufixo}`);
        const card = state?.closest(".jornada-card-item");
        if (!actual || !delta || !state) return;
        if (!evento?.efetiva) {
            actual.textContent = "--:--";
            delta.textContent = "Aguardando";
            if (card) { card.classList.remove("status-registered", "status-warning"); card.classList.add("status-pending"); }
            state.className = "jornada-state pending";
            state.innerHTML = '<span class="dot"></span>Pendente';
            return;
        }
        actual.textContent = evento.efetiva.horario;
        const diferenca = Number(evento.diferenca_minutos || 0);
        delta.textContent = diferenca === 0 ? "No horário" : `${diferenca > 0 ? "+" : ""}${diferenca} min`;
        const ok = Math.abs(Number(evento.diferenca_minutos || 0)) <= 5;
        if (card) { card.classList.remove("status-registered", "status-warning", "status-pending"); card.classList.add(ok ? "status-registered" : "status-warning"); }
        state.className = `jornada-state ${ok ? "registered" : "warning"}`;
        state.innerHTML = `<span class="dot"></span>${ok ? "Registrado" : "Diferença factual"}`;
    });
}

function dadosFiltrados() {
    const { status, cor, horario, ordem } = filtrosAplicados;
    const resultado = diasCarregados.filter((item) => {
        const pendente = ["incompleto", "sem_marcacao", "snapshot_ausente", "sem_evidencia"].includes(item.estado_informativo);
        if (status === "completo" && item.estado_informativo !== "completo") return false;
        if (status === "pendencia" && !pendente) return false;
        if (status === "sem_pendencia" && pendente) return false;
        if (cor && classificarStatusVisual(item) !== cor) return false;
        if (horario && !item.eventos?.some((evento) => classificarHorario(evento) === horario)) return false;
        return true;
    });
    return resultado.sort((a, b) => ordem === "desc"
        ? b.data_operacional.localeCompare(a.data_operacional)
        : a.data_operacional.localeCompare(b.data_operacional));
}

function classificarHorario(evento) {
    if (!evento?.efetiva) return "sem_batida";
    const diferenca = Math.abs(Number(evento.diferenca_minutos || 0));
    if (diferenca <= 5) return "ate_5";
    if (diferenca <= 10) return "de_6_a_10";
    return "acima_10";
}

function lerFiltrosAvancados() {
    filtrosAplicados = {
        status: document.getElementById("filtroStatus").value,
        cor: document.getElementById("filtroCor").value,
        horario: document.getElementById("filtroHorario").value,
        ordem: document.getElementById("filtroOrdem").value,
        itensPagina: Number(document.getElementById("itensPagina").value || 10),
    };
    paginaAtual = 1;
}

function classificarStatusVisual(item) {
    const eventos = item.eventos || [];
    const temRegistro = eventos.some((evento) => evento.efetiva);
    if (!temRegistro) return "sem_informacao";
    if (["incompleto", "sem_marcacao", "snapshot_ausente", "sem_evidencia"].includes(item.estado_informativo)) return "pendente";
    if (eventos.some((evento) => evento.efetiva && Math.abs(Number(evento.diferenca_minutos || 0)) > 5)) return "diferenca";
    return "coincidente";
}

function renderizarTabelaPontos() {
    const tbody = document.getElementById("tabela-pontos-body");
    const dados = dadosFiltrados();
    if (!dados.length) { document.getElementById("tablePagination").hidden = true; mostrarMensagemTabela("Nenhum registro encontrado para os filtros selecionados."); return; }
    const porPagina = filtrosAplicados.itensPagina;
    const totalPaginas = Math.max(1, Math.ceil(dados.length / porPagina));
    paginaAtual = Math.min(Math.max(paginaAtual, 1), totalPaginas);
    const inicio = (paginaAtual - 1) * porPagina;
    const pagina = dados.slice(inicio, inicio + porPagina);
    const hoje = hojeEmSaoPaulo();
    const estados = { coincidente: "Horário coincidente", diferenca: "Diferença factual", pendente: "Pendente RH/jurídico", sem_informacao: "Sem informação" };
    tbody.innerHTML = pagina.map((item) => {
        const ehHoje = item.data_operacional === hoje;
        const porTipo = Object.fromEntries((item.eventos || []).map((evento) => [evento.tipo, evento]));
        const hora = (tipo) => porTipo[tipo]?.efetiva?.horario || "--:--";
        const indicador = (tipo) => porTipo[tipo]?.indicador_tempo || "";
        const diferenca = (tipo) => porTipo[tipo]?.diferenca_minutos;
        const ajustada = (item.eventos || []).some((evento) => evento.efetiva?.ajustada);
        const visual = classificarStatusVisual(item);
        return `<tr class="${ehHoje ? "hoje" : ""}"><td>${ehHoje ? '<span class="hoje-badge">Hoje</span>' : ""}${ajustada ? '<span class="hoje-badge">Ajustado</span>' : ""}<br><small>${formatarDataBR(item.data_operacional)}</small></td><td>${criarCelulaHora(hora("entrada"), indicador("entrada"), diferenca("entrada"))}</td><td>${criarCelulaHora(hora("saida_intervalo"), indicador("saida_intervalo"), diferenca("saida_intervalo"))}</td><td>${criarCelulaHora(hora("retorno_intervalo"), indicador("retorno_intervalo"), diferenca("retorno_intervalo"))}</td><td>${criarCelulaHora(hora("saida"), indicador("saida"), diferenca("saida"))}</td><td><span class="total-horas">${item.duracao_descritiva || "--"}</span></td><td><span class="status-dia status-dia-${visual}"><span class="dot"></span>${estados[visual]}</span></td></tr>`;
    }).join("");
    const paginacao = document.getElementById("tablePagination");
    paginacao.hidden = totalPaginas <= 1;
    document.getElementById("paginationSummary").textContent = `Mostrando ${inicio + 1}–${Math.min(inicio + porPagina, dados.length)} de ${dados.length} dias`;
    document.getElementById("paginationPage").textContent = `${paginaAtual} / ${totalPaginas}`;
    document.getElementById("paginaAnterior").disabled = paginaAtual <= 1;
    document.getElementById("proximaPagina").disabled = paginaAtual >= totalPaginas;
}

async function carregarTabelaPontos() {
    try {
        const params = parametrosSelecionados();
        const payload = await apiJson(`/api/gestao/espelho?${params.toString()}`);
        diasCarregados = payload.dias || [];
        atualizarResumoLateral(diasCarregados);
        atualizarCardsJornada(diasCarregados);
        renderizarTabelaPontos();
    } catch (erro) {
        mostrarMensagemTabela(erro.message);
    }
}

async function atualizarFuncionarioSelecionado() {
    const funcionarioId = document.getElementById("filtroUsuario").value;
    if (!funcionarioId) {
        limparJornada();
        mostrarMensagemTabela("Selecione um funcionário.");
        return;
    }
    try {
        paginaAtual = 1;
        await Promise.all([carregarJornada(funcionarioId), carregarTabelaPontos()]);
    } catch (erro) {
        limparJornada(erro.message);
        mostrarMensagemTabela(erro.message);
    }
}

async function exportarPontos() {
    try {
        const params = parametrosSelecionados(true);
        const resposta = await fetch(`/api/gestao/espelho/exportar?${params.toString()}`, {
            credentials: "same-origin",
        });
        if (!resposta.ok) {
            let payload = null;
            try { payload = await resposta.json(); } catch (_erro) { payload = null; }
            throw new Error(payload?.erro || mensagemPadrao(resposta.status));
        }
        const blob = await resposta.blob();
        const formato = document.getElementById("exportFormat").value;
        const extensao = formato === "word" || formato === "doc" ? "docx" : formato;
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `espelho_ponto.${extensao}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
    } catch (erro) {
        alert(erro.message);
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    ativarListasSuspensas();
    preencherPeriodoPadrao();
    if (window.flatpickr) {
        const config = { dateFormat: "d/m/Y", locale: "pt", disableMobile: true, monthSelectorType: "static" };
        window.flatpickr("#dataInicio", config);
        window.flatpickr("#dataFim", config);
    }
    document.getElementById("btnPesquisar").addEventListener("click", () => { lerFiltrosAvancados(); atualizarFuncionarioSelecionado(); });
    document.querySelector(".btn-export").addEventListener("click", exportarPontos);
    document.getElementById("btnFiltrosAvancados").addEventListener("click", (event) => {
        const panel = document.getElementById("advancedFilters");
        const aberto = panel.hidden;
        panel.hidden = !aberto;
        event.currentTarget.setAttribute("aria-expanded", String(aberto));
    });
    document.getElementById("paginaAnterior").addEventListener("click", () => { paginaAtual -= 1; renderizarTabelaPontos(); });
    document.getElementById("proximaPagina").addEventListener("click", () => { paginaAtual += 1; renderizarTabelaPontos(); });
    try {
        await carregarFuncionarios();
        await atualizarFuncionarioSelecionado();
    } catch (erro) {
        mostrarMensagemTabela(erro.message);
    }
});
