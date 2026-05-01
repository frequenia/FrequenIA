const TOLERANCIA_MINUTOS = 5;
let jornadaPadrao = null;

function horaParaMinutos(hora) {
    if (!hora || hora === "--:--") return null;

    const [h, m] = hora.split(":").map(Number);
    return h * 60 + m;
}

function classificarHorario(tipo, valor) {
    if (!valor || valor === "--:--" || !jornadaPadrao) {
        return "";
    }

    const real = horaParaMinutos(valor);
    const esperado = horaParaMinutos(jornadaPadrao[tipo]);

    if (real === null || esperado === null) {
        return "";
    }

    if (tipo === "entrada" || tipo === "volta_intervalo") {
        if (real <= esperado) return "ok";
        if (real <= esperado + TOLERANCIA_MINUTOS) return "alerta";
        return "erro";
    }

    if (tipo === "saida_intervalo" || tipo === "saida") {
        if (real >= esperado) return "ok";
        if (real >= esperado - TOLERANCIA_MINUTOS) return "alerta";
        return "erro";
    }

    return "ok";
}

function criarCelulaHora(valor, tipo) {
    if (!valor || valor === "--:--") {
        return `<div class="hora">--:--</div>`;
    }

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
    try {
        const resp = await fetch("/jornada");

        if (!resp.ok) {
            console.error("Erro ao buscar jornada:", resp.status);
            return;
        }

        jornadaPadrao = await resp.json();

        document.getElementById("hora-entrada").textContent = jornadaPadrao.entrada ?? "--:--";
        document.getElementById("hora-saida-intervalo").textContent = jornadaPadrao.saida_intervalo ?? "--:--";
        document.getElementById("hora-volta-intervalo").textContent = jornadaPadrao.volta_intervalo ?? "--:--";
        document.getElementById("hora-saida").textContent = jornadaPadrao.saida ?? "--:--";

    } catch (erro) {
        console.error("Falha ao carregar jornada:", erro);
    }
}

async function carregarTabelaPontos() {
    const tbody = document.getElementById("tabela-pontos-body");

    try {
        const dataInicio = document.getElementById("dataInicio").value;
        const dataFim = document.getElementById("dataFim").value;
        const usuarioId = document.getElementById("filtroUsuario")?.value || "";

        const params = new URLSearchParams();

        if (dataInicio) {
            params.append("inicio", converterDataParaIso(dataInicio));
        }

        if (dataFim) {
            params.append("fim", converterDataParaIso(dataFim));
        }

        if (usuarioId) {
            params.append("usuario_id", usuarioId);
        }

        let url = "/pontos";

        if (params.toString()) {
            url += `?${params.toString()}`;
        }

        const resp = await fetch(url);

        if (!resp.ok) {
            throw new Error("Erro ao buscar dados");
        }

        const dados = await resp.json();

        if (!dados.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align:center;">Nenhum registro encontrado.</td>
                </tr>
            `;
            return;
        }

        const hoje = new Date().toISOString().split("T")[0];

        tbody.innerHTML = dados.map(item => {
            const ehHoje = item.data === hoje;

            return `
                <tr class="${ehHoje ? 'hoje' : ''}">
                    <td>
                        <span class="dia-label">${item.dia}</span>
                        ${ehHoje ? '<span class="hoje-badge">Hoje</span>' : ''}
                        <br>
                        <small>${formatarDataBR(item.data)}</small>
                    </td>

                    <td>${criarCelulaHora(item.entrada, "entrada")}</td>
                    <td>${criarCelulaHora(item.saida_intervalo, "saida_intervalo")}</td>
                    <td>${criarCelulaHora(item.volta_intervalo, "volta_intervalo")}</td>
                    <td>${criarCelulaHora(item.saida, "saida")}</td>

                    <td><span class="total-horas">${item.total}</span></td>
                </tr>
            `;
        }).join("");

    } catch (erro) {
        console.error(erro);

        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align:center;">Erro ao carregar dados.</td>
            </tr>
        `;
    }
}

function exportarPontos() {
    const formato = document.getElementById("exportFormat").value;
    const dataInicio = document.getElementById("dataInicio").value;
    const dataFim = document.getElementById("dataFim").value;
    const usuarioId = document.getElementById("filtroUsuario")?.value || "";

    if (!formato) {
        alert("Selecione um formato para exportação.");
        return;
    }

    const params = new URLSearchParams();
    params.append("formato", formato);

    if (dataInicio) {
        params.append("inicio", converterDataParaIso(dataInicio));
    }

    if (dataFim) {
        params.append("fim", converterDataParaIso(dataFim));
    }

    if (usuarioId) {
        params.append("usuario_id", usuarioId);
    }

    window.location.href = `/exportar-pontos?${params.toString()}`;
}

document.addEventListener("DOMContentLoaded", async () => {
    await carregarJornadaPadrao();
    await carregarTabelaPontos();

    const btnPesquisar = document.getElementById("btnPesquisar");
    if (btnPesquisar) {
        btnPesquisar.addEventListener("click", carregarTabelaPontos);
    }

    const btnExportar = document.querySelector(".btn-export");
    if (btnExportar) {
        btnExportar.addEventListener("click", exportarPontos);
    }
});