#!/usr/bin/env bash
set -euo pipefail
umask 077
private_dir='/mnt/c/Users/lavin/FrequenIA-backup-private'
repo_dir='/mnt/c/Users/lavin/Downloads/FrequenIA'
[[ "$PWD" == "$private_dir" ]] || exit 1
marker="$(mktemp "$private_dir/.profile-027-backup-start-XXXXXX")"
# O script histórico pode estar em checkout CRLF; não altera sua lógica.
bash <(tr -d '\r' < "$repo_dir/infra/aws/scripts/backup-current-supabase-operator.sh")
mapfile -t backups < <(find "$private_dir" -maxdepth 1 -type f -name 'supabase-pilot-*.dump.gpg' -newer "$marker" -printf '%f\n')
[[ ${#backups[@]} -eq 1 ]] || { printf 'Backup novo ambiguo; ensaio nao iniciado.\n'; exit 1; }
backup="${backups[0]}"
checksum="$(sha256sum "$private_dir/$backup" | awk '{print $1}')"
bash "$repo_dir/infra/aws/scripts/rehearse-current-profile-027-operator.sh" "$backup" "$checksum"
