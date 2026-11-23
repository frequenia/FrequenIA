(() => {
  const nameMessage = "Nome deve conter apenas letras, espaços, apóstrofos, pontos ou hífens, sem números (máximo de 160 caracteres).";
  const phoneMessage = "Informe o DDD e 8 dígitos para fixo ou 9 para celular iniciado em 9 (10 ou 11 dígitos ao todo, sem +55).";
  const personalNameValid = value => {
    const name = value.trim().normalize("NFC");
    return name.length > 0 && [...name].length <= 160 && /\p{L}/u.test(name) && /^[\p{L}\p{M} .’'\-]+$/u.test(name);
  };
  const phoneValid = value => !value.trim() || (value.trim().length <= 15 && /^[0-9()\s-]+$/.test(value) && /^[1-9][0-9](?:[0-9]{8}|9[0-9]{8})$/.test(value.replace(/\D/g, "")));
  function cpfValid(value) {
    if (!/^[0-9.\s-]+$/.test(value)) return false;
    const cpf = value.replace(/\D/g, "");
    if (cpf.length !== 11 || /^(\d)\1+$/.test(cpf)) return false;
    const numbers = [...cpf].map(Number);
    const digit = length => {
      const sum = numbers.slice(0, length).reduce((total, number, index) => total + number * (length + 1 - index), 0);
      const remainder = sum % 11;
      return remainder < 2 ? 0 : 11 - remainder;
    };
    return digit(9) === numbers[9] && digit(10) === numbers[10];
  }
  function formatPhone(value) {
    if (/[^0-9()\s-]/.test(value)) return value;
    const digits = value.replace(/\D/g, "");
    if (digits.length > 11) return value;
    if (digits.length <= 2) return digits;
    const local = digits.slice(2), split = digits.length > 10 ? 5 : 4;
    return `(${digits.slice(0, 2)}) ${local.slice(0, split)}${local.length > split ? "-" + local.slice(split) : ""}`;
  }
  function errorNode(field) {
    const id = `erro-${field.id}`;
    let node = document.getElementById(id);
    if (!node) {
      node = document.createElement("p"); node.id = id; node.className = "field-error"; node.hidden = true;
      (field.closest(".campo, .field") || field.parentElement).append(node);
      const ids = new Set((field.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean)); ids.add(id);
      field.setAttribute("aria-describedby", [...ids].join(" "));
    }
    return node;
  }
  function showFieldError(field, text) {
    if (!field) return;
    const node = errorNode(field); node.textContent = text; node.hidden = !text;
    if (text) field.setAttribute("aria-invalid", "true"); else field.removeAttribute("aria-invalid");
    const visible = field._flatpickr?.altInput;
    if (visible) { visible.setAttribute("aria-describedby", node.id); if (text) visible.setAttribute("aria-invalid", "true"); else visible.removeAttribute("aria-invalid"); }
  }
  function label(field) {
    const element = field.labels?.[0] || [...document.querySelectorAll("label")].find(item => item.htmlFor === field.id);
    return element?.textContent.replace(/\(opcional\)/i, "").trim() || "este campo";
  }
  function message(field) {
    if (field.validity.customError) return field.validationMessage;
    if (field.validity.valueMissing) return `${field.tagName === "SELECT" ? "Selecione" : "Informe"} ${label(field).toLowerCase()}.`;
    if (field.validity.typeMismatch && field.type === "email") return "Informe um e-mail válido, como nome@exemplo.com.";
    if (field.validity.rangeUnderflow || field.validity.rangeOverflow) return `${label(field)} deve ficar entre ${field.min} e ${field.max}.`;
    return field.validationMessage || "Confira o valor informado.";
  }
  function checkCustom(field) {
    if (field.matches("[data-cpf]")) field.setCustomValidity(!field.value.trim() ? "Informe o CPF." : cpfValid(field.value) ? "" : "CPF inválido. Confira os 11 dígitos e os dígitos verificadores.");
    if (field.matches("[data-person-name]")) field.setCustomValidity(!field.value.trim() ? "Informe o nome completo." : personalNameValid(field.value) ? "" : nameMessage);
    if (field.matches("[data-br-phone]")) field.setCustomValidity(field.required && !field.value.trim() ? "Informe o telefone com DDD." : phoneValid(field.value) ? "" : phoneMessage);
  }
  function summary(form, text) {
    let node = form.querySelector(".validation-summary");
    if (!node) { node = document.createElement("div"); node.className = "validation-summary"; node.setAttribute("role", "alert"); (form.querySelector(".page-header") || null)?.after(node); if (!node.parentNode) form.prepend(node); }
    node.textContent = text; node.hidden = !text;
  }
  function focus(field) {
    (field._flatpickr?.altInput || field.closest(".custom-select")?.querySelector(".select-trigger") || field).focus();
  }
  function validate(form) {
    summary(form, "");
    const invalid = [];
    [...form.elements].forEach(field => {
      if (!field.willValidate && !(field.required && field._flatpickr)) return;
      checkCustom(field);
      const text = field.required && field._flatpickr && !field.value ? `Informe ${label(field).toLowerCase()}.` : field.validity.valid ? "" : message(field); showFieldError(field, text);
      if (text) invalid.push(field);
    });
    if (invalid.length) { summary(form, "Não foi possível salvar. Revise os campos destacados abaixo."); focus(invalid[0]); }
    return invalid.length === 0;
  }
  function serverErrors(form, result) {
    let first;
    Object.entries(result.campos || {}).forEach(([key, text]) => {
      const field = [...form.elements].find(element => (element.dataset.serverField || element.id) === key);
      if (field && typeof text === "string") { showFieldError(field, text); first ||= field; }
    });
    summary(form, result.mensagem || result.erro || "Não foi possível salvar. Confira os dados informados.");
    if (first) focus(first);
  }
  function clear(form) {
    summary(form, "");
    [...form.elements].filter(field => field.matches("input, select, textarea")).forEach(field => { field.setCustomValidity(""); if (field.id) showFieldError(field, ""); });
  }
  function bind(form) {
    form.noValidate = true;
    form.addEventListener("invalid", event => { event.preventDefault(); showFieldError(event.target, message(event.target)); }, true);
    form.querySelectorAll("input, select").forEach(field => {
      if (field.matches("[data-br-phone]")) {
        field.maxLength = 15; field.inputMode = "tel";
        field.addEventListener("input", () => { field.value = formatPhone(field.value); });
        field.addEventListener("paste", event => { event.preventDefault(); field.value = formatPhone(event.clipboardData.getData("text")); field.dispatchEvent(new Event("input", {bubbles:true})); });
      }
      const update = () => { if (!field.willValidate && !field._flatpickr) return; checkCustom(field); if (field.hasAttribute("aria-invalid")) showFieldError(field, field.required && field._flatpickr && !field.value ? `Informe ${label(field).toLowerCase()}.` : field.validity.valid ? "" : message(field)); };
      field.addEventListener("input", update); field.addEventListener("change", update);
    });
    form.addEventListener("reset", () => clear(form));
  }
  window.CadastroValidation = {personalNameValid, phoneValid, cpfValid, formatPhone, validate, serverErrors, showFieldError, clear};
  document.querySelectorAll("form[data-validate-registration]").forEach(bind);
})();
