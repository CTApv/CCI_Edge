"""Package a committed stable tag without local runtime data or credentials."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+(?:\.\d+)?', args.tag):
        parser.error('Expected a stable version tag such as v1.4')
    sha = subprocess.check_output(['git', 'rev-parse', f'{args.tag}^{{commit}}'], cwd=root, text=True).strip()
    args.out.mkdir(parents=True, exist_ok=True)
    archive = args.out / f'pv-guardian-{args.tag}.tar.gz'
    subprocess.run(['git', 'archive', '--format=tar.gz', '-o', str(archive.resolve()), args.tag], cwd=root, check=True)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (args.out / 'SHA256SUMS').write_text(f'{digest}  {archive.name}\n', encoding='utf8')
    manifest = {'name': 'PV Guardian', 'version': args.tag, 'commit': sha, 'prerelease': False,
        'platform': 'linux/arm64', 'archive': archive.name, 'sha256': digest,
        'images': {component: f'ghcr.io/ctapv/pv-guardian-edge-{component}:{args.tag}' for component in ['backend', 'web']},
        'installation': 'deployment/docker/deploy-compose-release.sh',
        'default_web_port': 80, 'default_api_port': 8000,
        'validation_note': 'Consult individual catalog profiles for hardware validation status.'}
    (args.out / 'release-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'archive': str(archive), 'commit': sha, 'sha256': digest}))


if __name__ == '__main__':
    main()
