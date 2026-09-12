const TOLERANCIA_MINUTOS = 5;
let jornadaPadrao = null;

function horaParaMinutos(hora) {
    if (!hora || hora === "--:--") return null;
    const [h, m] = hora.split(":").map(Number);
    return h * 60 + m;
}

function classificarHorario(tipo, valor) {
    if (!valor || valor === "--:--" || !jornadaPadrao) return "";
    const real = horaParaMinutos(valor);
    const esperado = horaParaMinutos(jornadaPadrao[tipo]);
    if (real === null || esperado === null) return "";
    const diferenca = Math.abs(real - esperado);
    if (diferenca === 0) return "ok";
    if (diferenca <= TOLERANCIA_MINUTOS) return "alerta";
    return "erro";
}

function criarCelulaHora(valor, tipo) {
    if (!valor || valor === "--:--") return `<div class="hora">--:--</div>`;
    const classe = classificarHorario(tipo, valor);
    return `<div class="hora ${classe}">${valor}</div>`;
}

function formatarDataBR(dataIso) {
    const [ano, mes, dia] = dataIso.split("-");
    return `${dia}/${mes}/${ano}`;
}

function converterDataParaIso(dataBr) {
    if (!dataBr) return "";
    const [dia, mes, ano] = dataBr.split("/");
    return `${ano}-${mes}-${dia}`;
}

async function carregarJornadaPadrao() {
    jornadaPadrao = null;
    document.getElementById("hora-entrada").textContent = "--:--";
    document.getElementById("hora-saida-intervalo").textContent = "--:--";
    document.getElementById("hora-volta-intervalo").textContent = "--:--";
    document.getElementById("hora-saida").textContent = "--:--";
}

async function carregarFuncionarios() {
    const select = document.getElementById("filtroUsuario");
    if (!select) return;
    const resp = await fetch("/api/gestao/funcionarios");
    if (!resp.ok) throw new Error("Erro ao carregar funcionários");
    const funcionarios = await resp.json();
    select.innerHTML = '<option value="">Selecione</option>' + funcionarios.map(item =>
        `<option value="${item.funcionario_id}">${item.nome}${item.matricula ? ` - ${item.matricula}` : ""}</option>`
    ).join("");
}

async function carregarTabelaPontos() {
    const tbody = document.getElementById("tabela-pontos-body");
    try {
        const dataInicio = document.getElementById("dataInicio").value;
        const dataFim = document.getElementById("dataFim").value;
        const funcionarioId = document.getElementById("filtroUsuario")?.value || "";

        if (!funcionarioId) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Selecione um funcionário.</td></tr>';
            return;
        }

        const params = new URLSearchParams({ funcionario_id: funcionarioId });
        if (dataInicio) params.append("inicio", converterDataParaIso(dataInicio));
        if (dataFim) params.append("fim", converterDataParaIso(dataFim));

        const resp = await fetch(`/api/gestao/pontos?${params.toString()}`);
        if (!resp.ok) throw new Error("Erro ao buscar dados");
        const dados = await resp.json();

        if (!dados.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Nenhum registro encontrado.</td></tr>';
            return;
        }

        const hoje = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());
        tbody.innerHTML = dados.map(item => {
            const ehHoje = item.data === hoje;
            return `<tr class="${ehHoje ? "hoje" : ""}">
                <td><span class="dia-label">${item.dia}</span>${ehHoje ? '<span class="hoje-badge">Hoje</span>' : ""}<br><small>${formatarDataBR(item.data)}</small></td>
                <td>${criarCelulaHora(item.entrada, "entrada")}</td>
                <td>${criarCelulaHora(item.saida_intervalo, "saida_intervalo")}</td>
                <td>${criarCelulaHora(item.volta_intervalo, "volta_intervalo")}</td>
                <td>${criarCelulaHora(item.saida, "saida")}</td>
                <td><span class="total-horas">${item.total}</span></td>
            </tr>`;
        }).join("");
    } catch (erro) {
        console.error(erro);
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Erro ao carregar dados.</td></tr>';
    }
}

function exportarPontos() {
    alert("A exportação ainda usa o fluxo legado e será migrada em uma próxima etapa.");
}

document.addEventListener("DOMContentLoaded", async () => {
    try { await carregarFuncionarios(); } catch (erro) { console.error(erro); }
    await carregarJornadaPadrao();
    await carregarTabelaPontos();

    const btnPesquisar = document.getElementById("btnPesquisar");
    if (btnPesquisar) btnPesquisar.addEventListener("click", carregarTabelaPontos);
    const btnExportar = document.querySelector(".btn-export");
    if (btnExportar) btnExportar.addEventListener("click", exportarPontos);
});
