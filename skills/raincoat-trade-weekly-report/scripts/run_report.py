#!/usr/bin/env python3
"""Validate the six-file input contract and invoke the bundled report generator."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', type=Path)
    parser.add_argument('output_file', nargs='?', type=Path)
    parser.add_argument('--input-dir', '--data-dir', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--run-id', help='Optional label printed in the local run log; not an archive identifier')
    args = parser.parse_args()
    source = args.input_dir or args.input
    if source is None or (args.input_dir and args.input):
        parser.error('provide exactly one input directory')
    if sum(x is not None for x in [args.output_dir, args.output, args.output_file]) > 1:
        parser.error('provide only one output location')
    source = source.expanduser().resolve()
    required = ['整体.xlsx', '行业.xlsx', '流量.xlsx', '内容类型.xlsx', '商家标签.xlsx']
    missing = [f for f in required if not (source / f).is_file()]
    if not any((source / name).is_file() for name in ['商品明细.xlsx', '商品.xlsx']):
        missing.append('商品明细.xlsx (or 商品.xlsx)')
    if missing:
        parser.error('missing input files: ' + ', '.join(missing))
    output = args.output or args.output_file or ((args.output_dir or source) / 'report.html')
    output = output.expanduser().resolve()
    if args.run_id:
        print(f'Run label: {args.run_id}', flush=True)
    return subprocess.run([sys.executable, str(Path(__file__).with_name('generate_report.py')),
                           '--data-dir', str(source), '--output', str(output)]).returncode


if __name__ == '__main__':
    sys.exit(main())
