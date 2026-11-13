const TIMEZONE_LOCAL = "America/Sao_Paulo";
let jornadaPadrao = null;

function criarCelulaHora(valor, indicador = "") {
    if (!valor || valor === "--:--") return '<div class="hora">--:--</div>';
    const classe = indicador === "no_horario" ? "ok" : (indicador ? "alerta" : "");
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
    inicio.setUTCDate(inicio.getUTCDate() - 30);
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
        exibirHoraPrevista("hora-entrada", primeiro, "inicio");
        exibirHoraPrevista("hora-saida", primeiro, "fim");
        return;
    }

    if (periodos.length === 2) {
        jornadaPadrao = {
            entrada: primeiro.inicio,
            saida_intervalo: primeiro.fim,
            retorno_intervalo: ultimo.inicio,
            saida: ultimo.fim,
        };
        exibirHoraPrevista("hora-entrada", primeiro, "inicio");
        exibirHoraPrevista("hora-saida-intervalo", primeiro, "fim");
        exibirHoraPrevista("hora-volta-intervalo", ultimo, "inicio");
        exibirHoraPrevista("hora-saida", ultimo, "fim");
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
    exibirHoraPrevista("hora-entrada", primeiro, "inicio");
    exibirHoraPrevista("hora-saida", ultimo, "fim");
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
    const data = dataReferenciaJornada();
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

async function carregarTabelaPontos() {
    const tbody = document.getElementById("tabela-pontos-body");
    try {
        const params = parametrosSelecionados();
        const payload = await apiJson(`/api/gestao/espelho?${params.toString()}`);
        const dados = payload.dias || [];
        if (!dados.length) {
            mostrarMensagemTabela("Nenhum registro encontrado.");
            return;
        }
        const hoje = hojeEmSaoPaulo();
        tbody.innerHTML = dados.map((item) => {
            const ehHoje = item.data_operacional === hoje;
            const porTipo = Object.fromEntries(
                (item.eventos || []).map((evento) => [evento.tipo, evento])
            );
            const hora = (tipo) => porTipo[tipo]?.efetiva?.horario || "--:--";
            const indicador = (tipo) => porTipo[tipo]?.indicador_tempo || "";
            const ajustada = (item.eventos || []).some((evento) => evento.efetiva?.ajustada);
            const estados = {
                completo: "Completo",
                incompleto: "Incompleto",
                sem_marcacao: "Sem marcação (indicativo)",
                folga: "Folga",
                folga_com_marcacao: "Folga com marcação",
                sem_jornada: "Sem jornada",
                sem_jornada_com_marcacao: "Sem jornada com marcação",
                snapshot_ausente: "Snapshot ausente",
                sem_evidencia: "Sem evidência",
            };
            return `<tr class="${ehHoje ? "hoje" : ""}">
                <td>${ehHoje ? '<span class="hoje-badge">Hoje</span>' : ""}${ajustada ? '<span class="hoje-badge">Ajustado</span>' : ""}<br><small>${formatarDataBR(item.data_operacional)}</small></td>
                <td>${criarCelulaHora(hora("entrada"), indicador("entrada"))}</td>
                <td>${criarCelulaHora(hora("saida_intervalo"), indicador("saida_intervalo"))}</td>
                <td>${criarCelulaHora(hora("retorno_intervalo"), indicador("retorno_intervalo"))}</td>
                <td>${criarCelulaHora(hora("saida"), indicador("saida"))}</td>
                <td><span class="total-horas">${item.duracao_descritiva || "--"}</span></td>
                <td>${estados[item.estado_informativo] || "Informativo"}</td>
            </tr>`;
        }).join("");
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
    preencherPeriodoPadrao();
    if (window.flatpickr) {
        const config = { dateFormat: "d/m/Y", locale: "pt", disableMobile: true };
        window.flatpickr("#dataInicio", config);
        window.flatpickr("#dataFim", config);
    }
    document.getElementById("filtroUsuario").addEventListener("change", atualizarFuncionarioSelecionado);
    document.getElementById("btnPesquisar").addEventListener("click", atualizarFuncionarioSelecionado);
    document.querySelector(".btn-export").addEventListener("click", exportarPontos);
    try {
        await carregarFuncionarios();
        await atualizarFuncionarioSelecionado();
    } catch (erro) {
        mostrarMensagemTabela(erro.message);
    }
});
