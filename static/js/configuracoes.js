document.addEventListener("DOMContentLoaded", function () {
  const btnSalvar = document.getElementById("salvar-config");
  const btnCancelar = document.getElementById("cancelar-config");

  // Carrega o tema salvo e marca o radio correto
  const temaSalvo = localStorage.getItem("tema") || "light";
  const radioTema = document.querySelector(`input[name="tema"][value="${temaSalvo}"]`);

  if (radioTema) {
    radioTema.checked = true;
  }

  if (btnSalvar) {
    btnSalvar.addEventListener("click", function () {
      const selecionado = document.querySelector('input[name="tema"]:checked');

      if (!selecionado) {
        alert("Selecione um tema.");
        return;
      }

      const tema = selecionado.value;

      // salva no navegador
      localStorage.setItem("tema", tema);

      // se existir função global no dark-mode.js, chama ela
      if (typeof window.aplicarTema === "function") {
        window.aplicarTema(tema);
      }
    });
  }

  if (btnCancelar) {
    btnCancelar.addEventListener("click", function () {
      const temaAtual = localStorage.getItem("tema") || "light";
      const radioAtual = document.querySelector(`input[name="tema"][value="${temaAtual}"]`);

      if (radioAtual) {
        radioAtual.checked = true;
      }
    });
  }
});