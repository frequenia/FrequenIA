#!/usr/bin/env bash
set -euo pipefail
# A tag esperada pelo boot deve acompanhar a tag imutável da publicação.
# Não altera a AWS. Preserva um destino local já existente.
image="${1:?Informe a tag revisada da imagem local}"
output="${2:?Informe caminho novo para o pacote}"
[[ "$image" =~ ^frequenia:pilot-[a-z0-9-]+$ ]] || exit 1
[[ ! -e "$output" ]] || { printf 'Pacote ja existe; nada sobrescrito.\n'; exit 1; }
[[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]] || exit 1
layers="$(docker image inspect "$image" --format '{{len .RootFS.Layers}}')"
[[ "$layers" =~ ^[0-9]+$ && "$layers" -le 125 ]] || {
    printf 'Imagem excede 125 camadas; empacotamento interrompido antes da troca de tag.\n'
    exit 1
}
docker tag "$image" frequenia:pilot
docker save "$image" frequenia:pilot | gzip -1 > "$output"
gzip -t "$output"
sha256sum "$output"
