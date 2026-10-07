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

document.addEventListener("DOMContentLoaded", async function () {
  const card = document.getElementById("geofence-card");
  const unitSelect = document.getElementById("geofence-unidade");
  if (!card || !unitSelect) return;
  const status = document.getElementById("geofence-status");
  const setStatus = (message, error = false) => {
    status.textContent = message;
    status.style.color = error ? "#b42318" : "";
  };
  const latitudeInput = document.getElementById("geofence-latitude");
  const longitudeInput = document.getElementById("geofence-longitude");
  const map = document.getElementById("geofence-mapa");
  const mapWrap = document.getElementById("geofence-mapa-wrap");
  const refreshMap = async () => {
    if (!latitudeInput.value || !longitudeInput.value) {
      mapWrap.hidden = true;
      return;
    }
    const latitude = Number(latitudeInput.value);
    const longitude = Number(longitudeInput.value);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    try {
      const data = await requestJson(`/api/admin/geocodificacao/mapa?latitude=${latitude}&longitude=${longitude}`);
      map.src = `data:image/png;base64,${data.mapa_png_base64}`;
      map.dataset.zoom = data.zoom;
      mapWrap.hidden = false;
    } catch (_) { mapWrap.hidden = true; }
  };
  const requestJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.erro || "Não foi possível concluir a operação.");
    return data;
  };
  try {
    const response = await fetch("/listar_unidades");
    if (response.status === 403) return;
    if (!response.ok) throw new Error("Não foi possível carregar as unidades.");
    const units = await response.json();
    units.forEach((unit) => unitSelect.add(new Option(unit.nome, unit.id)));
    card.hidden = false;
  } catch (error) {
    setStatus(error.message, true);
    card.hidden = false;
  }

  unitSelect.addEventListener("change", async () => {
    if (!unitSelect.value) return;
    try {
      const {unidade} = await requestJson(`/api/admin/unidades/${unitSelect.value}/geofence`);
      document.getElementById("geofence-latitude").value = unidade.latitude ?? "";
      document.getElementById("geofence-longitude").value = unidade.longitude ?? "";
      document.getElementById("geofence-raio").value = unidade.raio_metros ?? 150;
      document.getElementById("geofence-endereco").value = unidade.endereco ?? "";
      document.getElementById("geofence-ativa").checked = unidade.marcacao_mobile_ativa === true;
      await refreshMap();
      setStatus("");
    } catch (error) { setStatus(error.message, true); }
  });

  document.getElementById("geofence-buscar").addEventListener("click", async () => {
    const query = document.getElementById("geofence-busca").value.trim();
    const results = document.getElementById("geofence-resultados");
    results.replaceChildren();
    try {
      const data = await requestJson(`/api/admin/geocodificacao?q=${encodeURIComponent(query)}`);
      data.resultados.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-secondary";
        button.textContent = item.endereco;
        button.addEventListener("click", () => {
          document.getElementById("geofence-latitude").value = item.latitude;
          document.getElementById("geofence-longitude").value = item.longitude;
          document.getElementById("geofence-endereco").value = item.endereco;
          results.replaceChildren();
          refreshMap();
        });
        results.appendChild(button);
      });
      if (!data.resultados.length) setStatus("Nenhum endereço encontrado.", true);
    } catch (error) { setStatus(error.message, true); }
  });

  document.getElementById("geofence-salvar").addEventListener("click", async () => {
    if (!unitSelect.value) return setStatus("Selecione uma unidade.", true);
    if (!latitudeInput.value || !longitudeInput.value) return setStatus("Informe coordenadas válidas.", true);
    try {
      await requestJson(`/api/admin/unidades/${unitSelect.value}/geofence`, {
        method: "PUT",
        body: JSON.stringify({
          latitude: Number(document.getElementById("geofence-latitude").value),
          longitude: Number(document.getElementById("geofence-longitude").value),
          endereco: document.getElementById("geofence-endereco").value,
          raio_metros: Number(document.getElementById("geofence-raio").value),
          ativa: document.getElementById("geofence-ativa").checked,
        }),
      });
      setStatus("Configuração salva e auditada.");
    } catch (error) { setStatus(error.message, true); }
  });

  map.addEventListener("click", (event) => {
    const rect = map.getBoundingClientRect();
    const zoom = Number(map.dataset.zoom || 17);
    const scaleX = map.naturalWidth / rect.width;
    const scaleY = map.naturalHeight / rect.height;
    const dx = (event.clientX - rect.left - rect.width / 2) * scaleX;
    const dy = (event.clientY - rect.top - rect.height / 2) * scaleY;
    const world = 256 * 2 ** zoom;
    const lon = Number(longitudeInput.value);
    const lat = Number(latitudeInput.value);
    const x = ((lon + 180) / 360) * world + dx;
    const sinLat = Math.sin(lat * Math.PI / 180);
    const y = (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * world + dy;
    longitudeInput.value = (x / world * 360 - 180).toFixed(7);
    const n = Math.PI - 2 * Math.PI * y / world;
    latitudeInput.value = (180 / Math.PI * Math.atan(Math.sinh(n))).toFixed(7);
    refreshMap();
  });
});
