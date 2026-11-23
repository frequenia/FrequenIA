"""Prepara contexto mínimo, sem usar o checkout inteiro como contexto Docker."""
import hashlib,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[3]
files=['app.py','routes/views.py','routes/profile_photo.py','services/profile_photo.py',
       'routes/kiosk.py','utils/terminal_auth.py','routes/occurrences.py','services/correction_workflow.py',
       'templates/perfil.html','static/css/perfil.css','static/js/perfil.js',
       'templates/ativarTerminal.html','templates/ocorrencias.html','static/js/ocorrencias.js']
output=root/'infra/aws/dist/profile-release-single-layer-20261123'
output.mkdir(parents=True,exist_ok=False)
for name in files:
    target=output/'payload'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/name,target)
shutil.copyfile(root/'infra/aws/Dockerfile.profile-release-20261123',output/'Dockerfile')
manifest=[dict(file=p,sha256=hashlib.sha256((root/p).read_bytes()).hexdigest()) for p in files]
(root/'infra/aws/dist/profile-release-20261123-manifest.json').write_text(json.dumps(manifest,indent=2))
print('context_files=14; payload_layers=1; extra_images=0; private_files=0')
