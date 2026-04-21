function criarCelulaHora(valor) {
    if (!valor || valor === "--:--") {
        return `<div class="hora">--:--</div>`;
    }

    return `<div class="hora ok">${valor}</div>`;
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

async function carregarTabelaPontos() {
    const tbody = document.getElementById("tabela-pontos-body");

    try {
        const dataInicio = document.getElementById("dataInicio").value;
        const dataFim = document.getElementById("dataFim").value;

        const params = new URLSearchParams();

        if (dataInicio) {
            params.append("inicio", converterDataParaIso(dataInicio));
        }

        if (dataFim) {
            params.append("fim", converterDataParaIso(dataFim));
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

                    <td>${criarCelulaHora(item.entrada)}</td>
                    <td>${criarCelulaHora(item.saida_intervalo)}</td>
                    <td>${criarCelulaHora(item.volta_intervalo)}</td>
                    <td>${criarCelulaHora(item.saida)}</td>

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

    window.location.href = `/exportar-pontos?${params.toString()}`;
}

document.addEventListener("DOMContentLoaded", () => {
    carregarTabelaPontos();

    const btnPesquisar = document.getElementById("btnPesquisar");
    if (btnPesquisar) {
        btnPesquisar.addEventListener("click", carregarTabelaPontos);
    }

    const btnExportar = document.querySelector(".btn-export");
    if (btnExportar) {
        btnExportar.addEventListener("click", exportarPontos);
    }
});