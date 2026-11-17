document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("select[data-busca-funcionario]").forEach(select => {
    const wrapper = document.createElement("div");
    wrapper.className = "busca-funcionario";
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);
    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = "Buscar por nome ou matrícula";
    input.setAttribute("aria-label", input.placeholder);
    input.autocomplete = "off";
    if (select.required) {
      input.required = true;
      select.required = false;
    }
    const list = document.createElement("div");
    list.className = "busca-funcionario-lista";
    list.hidden = true;
    wrapper.insertBefore(input, select);
    wrapper.appendChild(list);
    select.classList.add("busca-funcionario-original");

    const normalize = value => value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
    function render() {
      list.replaceChildren();
      const term = normalize(input.value);
      const options = [...select.options].filter(option => !term || normalize(option.textContent).includes(term));
      options.forEach(option => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = option.textContent;
        button.addEventListener("click", () => {
          select.value = option.value;
          input.value = option.value ? option.textContent : "";
          list.hidden = true;
          select.dispatchEvent(new Event("change", { bubbles: true }));
        });
        list.appendChild(button);
      });
      if (!options.length) list.textContent = "Nenhum funcionário encontrado.";
    }
    input.addEventListener("focus", () => { render(); list.hidden = false; });
    input.addEventListener("input", () => {
      select.value = "";
      input.setCustomValidity(input.value ? "Selecione um funcionário da lista." : "");
      render();
      list.hidden = false;
    });
    input.addEventListener("keydown", event => {
      if (event.key === "Escape") { list.hidden = true; input.blur(); }
    });
    document.addEventListener("click", event => {
      if (!wrapper.contains(event.target)) {
        list.hidden = true;
        input.value = select.value ? select.selectedOptions[0].textContent : "";
      }
    });
    select.addEventListener("change", () => {
      input.value = select.value ? select.selectedOptions[0].textContent : "";
      input.setCustomValidity("");
    });
    select.addEventListener("invalid", () => input.focus());
  });

  if (window.flatpickr) {
    document.querySelectorAll('input[type="date"]').forEach(input => {
      const picker = window.flatpickr(input, {
        dateFormat: "Y-m-d",
        altInput: true,
        altFormat: "d/m/Y",
        locale: "pt",
        disableMobile: true,
        monthSelectorType: "static"
      });
      picker.altInput?.addEventListener("focus", () => {
        const displayed = picker.selectedDates[0] ? picker.formatDate(picker.selectedDates[0], "Y-m-d") : "";
        if (input.value !== displayed) picker.setDate(input.value, false, "Y-m-d");
      });
      input.form?.addEventListener("reset", () => {
        setTimeout(() => picker.setDate(input.value, false, "Y-m-d"), 0);
      });
    });
  }
});
