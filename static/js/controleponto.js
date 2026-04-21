
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

async function carregarTabelaPontos() {
    const tbody = document.getElementById("tabela-pontos-body");

    try {
        const resp = await fetch("/pontos");

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

document.addEventListener("DOMContentLoaded", carregarTabelaPontos);
