#!/usr/bin/env python3
"""Generate a report Skill from bundled templates without a parent repository."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

PACKAGE = Path(__file__).resolve().parents[1]
LABELS = {'L0': 'L0 Documentation', 'L1': 'L1 Runnable MVP', 'L2': 'L2 Publishable'}

def generate(args):
    if not re.fullmatch(r'raincoat-[a-z0-9]+(?:-[a-z0-9]+)*', args.name) or len(args.name) > 64:
        raise ValueError('Skill name must use raincoat-xxx, at most 64 characters.')
    aliases = {'documentation-only': 'L0', 'runnable': 'L1', 'publishable': 'L2', 'stable': 'L2'}
    level = aliases.get(args.level.lower(), args.level.upper())
    if level not in LABELS:
        raise ValueError('level must be L0, L1 or L2')
    spec, source = Path(args.spec).resolve(), Path(args.source).resolve()
    for path in (spec, source):
        if not path.is_file():
            raise ValueError(f'Input not found: {path}')
    target = Path(args.output_root).resolve() / args.name
    if target.exists():
        raise ValueError(f'Target exists: {target}')
    evidence = Path(args.evidence_dir).resolve() if args.evidence_dir else None
    if level != 'L0':
        required = ['scripts/run-report.sh', 'output/report.html', 'output/run.log', 'output/validation-report.json']
        if not evidence:
            raise ValueError(f'{level} requires real runner, sample-backed execution evidence, and validation evidence; provide --evidence-dir')
        for rel in required:
            if not (evidence / rel).is_file():
                raise ValueError(f'Missing evidence: {rel}')
        if not (evidence / 'sample_data').is_dir() or not any((evidence / 'sample_data').iterdir()):
            raise ValueError('sample_data must contain input evidence')
        if re.search(r'placeholder|replace this stub|currently marked as', (evidence / required[0]).read_text(), re.I):
            raise ValueError('Evidence runner is a stub')
        if level == 'L2':
            if not (evidence / 'output/browser-validation.json').is_file() or not (evidence / 'output/screenshots').is_dir() or not any((evidence / 'output/screenshots').iterdir()):
                raise ValueError('L2 requires browser evidence and screenshots')
    # Build in a temporary sibling: failures do not leave partial output.
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.report-build-', dir=target.parent) as tmp:
        stage = Path(tmp) / args.name
        for folder in ('assets', 'examples', 'scripts', 'agents'):
            (stage / folder).mkdir(parents=True)
        replacements = {'__SKILL_NAME__': args.name, '__SKILL_TITLE__': args.title,
                        '__SKILL_LEVEL__': level, '__SKILL_LEVEL_LABEL__': LABELS[level]}
        for template in (PACKAGE / 'assets/templates').glob('*.tpl'):
            name = template.name[:-4]
            if name == 'SKILL.md': rel = name
            elif name == 'agents.openai.yaml': rel = 'agents/openai.yaml'
            elif name in ('normalized-spec.md', 'normalized-spec-summary.md', 'input_inventory.md', 'output-outline.html'): rel = 'examples/' + name
            elif name == 'requirements.txt': rel = 'scripts/' + name
            else: rel = 'assets/' + name
            text = template.read_text(encoding='utf-8')
            for key, value in replacements.items(): text = text.replace(key, value)
            (stage / rel).write_text(text, encoding='utf-8')
        for src, rel in ((spec, 'examples/normalized-spec-full.md'), (source, 'examples/source-requirement.md')):
            shutil.copy2(src, stage / rel)
        for name in ('validation-contract.md', 'DESIGN.md', 'base-report.css', 'chart-defaults.js'):
            shutil.copy2(PACKAGE / 'assets' / name, stage / 'assets' / name)
        shutil.copy2(PACKAGE / 'scripts/validate-output-inventory.py', stage / 'scripts/validate-output-inventory.py')
        subprocess.run([sys.executable, str(PACKAGE / 'scripts/build-output-inventory.py'), '--spec', str(spec), '--output', str(stage / 'examples/expected-output-inventory.json')], check=True)
        gaps = ['runtime not implemented', 'browser validation not run'] if level == 'L0' else []
        # JSON is valid YAML; quote user-provided strings safely.
        manifest = {'version': 1, 'skill_name': args.name, 'skill_title': args.title,
                    'declared_level': level, 'effective_level': level,
                    'acceptance_status': 'documentation-only' if level == 'L0' else 'evidence-supplied-not-independently-verified',
                    'acceptance_date': date.today().isoformat(), 'blocking_gaps': gaps}
        (stage / 'skill-manifest.yaml').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        if level == 'L0':
            (stage / 'scripts/run_report.py').write_text('raise SystemExit("L0 documentation only: runtime not implemented")\n')
            runner = stage / 'scripts/run-report.sh'
            runner.write_text('#!/usr/bin/env bash\necho "L0 documentation only: runtime not implemented" >&2\nexit 1\n')
            runner.chmod(0o755)
        else:
            for folder in ('scripts', 'sample_data', 'output'):
                shutil.copytree(evidence / folder, stage / folder, dirs_exist_ok=True)
        (stage / 'README.md').write_text(f'# {args.name}\n\n{args.title}\n\nLevel: {level}. See SKILL.md and skill-manifest.yaml.\nLicense must be confirmed before publication.\n', encoding='utf-8')
        stage.rename(target)
    print(f'Created {target} ({LABELS[level]})')
    return target

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('name'); p.add_argument('title'); p.add_argument('spec'); p.add_argument('source')
    p.add_argument('level', nargs='?', default='L0')
    p.add_argument('--evidence-dir'); p.add_argument('--output-root', default=str(Path.cwd() / 'skills'))
    args = p.parse_args()
    try: generate(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        p.exit(1, f'{exc}\n')

if __name__ == '__main__': main()
