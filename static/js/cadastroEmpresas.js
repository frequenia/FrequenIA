function addTelefone() {
    const container = document.getElementById("telefones");

    const div = document.createElement("div");
    div.classList.add("telefone-linha");

div.innerHTML = `
    <select>
        <option>Fixo</option>
        <option>Celular</option>
    </select>

    <input type="text" placeholder="(xx) xxxxx-xxxx">

    <input type="text" placeholder="Setor ou responsável">

    <button type="button" class="btn btn-secondary btn-sm btn-remover">
        Remover
    </button>

    <button type="button" class="btn btn-primary btn-sm btn-add">
        +
    </button>
`;

    container.appendChild(div);

    div.querySelector(".btn-remover").addEventListener("click", () => {
        const total = document.querySelectorAll(".telefone-linha").length;

        if (total > 1) {
            div.remove();
        } else {
            alert("Deve haver pelo menos um telefone.");
        }
    });
    div.querySelector(".btn-add").addEventListener("click", addTelefone);
}

function addEmail() {
    const container = document.getElementById("emails");

    const div = document.createElement("div");
    div.classList.add("email-linha");

div.innerHTML = `
    <input type="email" placeholder="Digite o e-mail">

    <button type="button" class="btn btn-secondary btn-sm btn-remover-email">
        Remover
    </button>

    <button type="button" class="btn btn-primary btn-sm btn-add-email">
        +
    </button>
`;

    container.appendChild(div);

    div.querySelector(".btn-remover-email").addEventListener("click", () => {
        if (document.querySelectorAll(".email-linha").length > 1) {
            div.remove();
        } else {
            alert("Deve haver pelo menos um e-mail.");
        }
    });
    div.querySelector(".btn-add-email").addEventListener("click", addEmail);
}

// inicial
window.onload = () => {
    if (document.querySelectorAll(".telefone-linha").length === 0) {
        addTelefone();
    }

    if (document.querySelectorAll(".email-linha").length === 0) {
        addEmail();
    }
};

async function salvarEmpresa(){
    console.log("clicou");
    const dadosEmpresa = {
        cnpj: document.getElementById("cnpj").value,
        razao: document.getElementById("razao").value
    }

    const res = await fetch("http://127.0.0.1:5000/cadastrar_empresa", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dadosEmpresa),
  });
}