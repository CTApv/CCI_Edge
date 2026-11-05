"""Package a committed TEST SINVERT tag without runtime data or credentials."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('tag')
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
if not args.tag.startswith('v') or 'test-sinvert' not in args.tag:
    parser.error('Expected an explicit TEST SINVERT version tag')
sha=subprocess.check_output(['git','rev-parse',f'{args.tag}^{{commit}}'],cwd=root,text=True).strip()
args.out.mkdir(parents=True,exist_ok=True)
archive=args.out/f'pv-guardian-TEST-SINVERT-{args.tag}.tar.gz'
subprocess.run(['git','archive','--format=tar.gz','--prefix=pv-guardian-test-sinvert/',
                '-o',str(archive.resolve()),args.tag],cwd=root,check=True)
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(args.out/'SHA256SUMS').write_text(f'{digest}  {archive.name}\n',encoding='utf8')
manifest={'name':'TEST SINVERT','version':args.tag,'commit':sha,'base':'v1.2.0-rc2',
          'prerelease':True,'platform':'linux/arm64','archive':archive.name,'sha256':digest,
          'images':{'backend':f'ghcr.io/ctapv/pv-guardian-edge-backend:{args.tag}',
                    'web':f'ghcr.io/ctapv/pv-guardian-edge-web:{args.tag}'},
          'installation':'deployment/sinvert/manage-test-sinvert.sh',
          'default_web_port':18080,'default_api_port':18000,
          'field_control_validated':False}
(args.out/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print(json.dumps({'archive':str(archive),'commit':sha,'sha256':digest}))
