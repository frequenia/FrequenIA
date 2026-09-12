const TOLERANCIA_MINUTOS = 5;
const TIMEZONE_LOCAL = "America/Sao_Paulo";
let jornadaPadrao = null;

function horaParaMinutos(hora) {
    if (!hora || hora === "--:--") return null;
    const correspondencia = String(hora).match(/^(\d{2}):(\d{2})/);
    if (!correspondencia) return null;
    return Number(correspondencia[1]) * 60 + Number(correspondencia[2]);
}

function classificarHorario(tipo, valor) {
    if (!valor || valor === "--:--" || !jornadaPadrao) return "";
    const real = horaParaMinutos(valor);
    const esperado = horaParaMinutos(jornadaPadrao[tipo]);
    if (real === null || esperado === null) return "";
    const diferencaLinear = Math.abs(real - esperado);
    const diferenca = Math.min(diferencaLinear, 1440 - diferencaLinear);
    if (diferenca === 0) return "ok";
    if (diferenca <= TOLERANCIA_MINUTOS) return "alerta";
    return "erro";
}

function criarCelulaHora(valor, tipo) {
    if (!valor || valor === "--:--") return '<div class="hora">--:--</div>';
    const classe = classificarHorario(tipo, valor);
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
    celula.colSpan = 6;
    celula.style.textAlign = "center";
    celula.textContent = texto;
    linha.appendChild(celula);
    tbody.replaceChildren(linha);
}

async function carregarTabelaPontos() {
    const tbody = document.getElementById("tabela-pontos-body");
    try {
        const params = parametrosSelecionados();
        const dados = await apiJson(`/api/gestao/pontos?${params.toString()}`);
        if (!dados.length) {
            mostrarMensagemTabela("Nenhum registro encontrado.");
            return;
        }
        const hoje = hojeEmSaoPaulo();
        tbody.innerHTML = dados.map((item) => {
            const ehHoje = item.data === hoje;
            const retorno = item.retorno_intervalo || item.volta_intervalo;
            return `<tr class="${ehHoje ? "hoje" : ""}">
                <td><span class="dia-label">${item.dia}</span>${ehHoje ? '<span class="hoje-badge">Hoje</span>' : ""}<br><small>${formatarDataBR(item.data)}</small></td>
                <td>${criarCelulaHora(item.entrada, "entrada")}</td>
                <td>${criarCelulaHora(item.saida_intervalo, "saida_intervalo")}</td>
                <td>${criarCelulaHora(retorno, "retorno_intervalo")}</td>
                <td>${criarCelulaHora(item.saida, "saida")}</td>
                <td><span class="total-horas">${item.total}</span></td>
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
        const resposta = await fetch(`/exportar-pontos?${params.toString()}`, {
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
        link.download = `controle_ponto.${extensao}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
    } catch (erro) {
        alert(erro.message);
    }
}

document.addEventListener("DOMContentLoaded", async () => {
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
