function aplicarTema(tema) {
  const escuro = tema === "dark";

  document.body.classList.toggle("dark-mode", escuro);
  document.documentElement.classList.toggle("dark-mode", escuro);

  try {
    if (window.parent && window.parent !== window) {
      window.parent.document.body.classList.toggle("dark-mode", escuro);
      window.parent.document.documentElement.classList.toggle("dark-mode", escuro);
    }
  } catch (erro) {
    console.log("Não foi possível aplicar o tema na janela.");
  }
}

window.aplicarTema = aplicarTema;

document.addEventListener("DOMContentLoaded", function () {
  const temaSalvo = localStorage.getItem("tema") || "light";
  aplicarTema(temaSalvo);
});