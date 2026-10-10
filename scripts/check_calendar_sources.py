#!/usr/bin/env python3
"""Run the isolated source-to-release matrix and write a reviewable local receipt."""
import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = 'tests/services/test_calendar_sources_pipeline.py'


def main():
    parser = argparse.ArgumentParser(description='本地 HTTP fixture 验收，不连接真实飞书；跳过视为失败。')
    parser.add_argument('--output', type=Path, required=True, help='JSON 回执路径；同目录保存 JUnit 证据')
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = output.with_suffix('.junit.xml')
    if evidence == output:
        parser.error('--output 须使用 .json 扩展名')
    if evidence.exists():
        parser.error('JUnit 证据已存在，请使用新的回执路径，避免覆盖旧验收')
    completed = subprocess.run([sys.executable, '-m', 'pytest', '-q', TEST, '--junitxml=' + str(evidence)],
                               cwd=ROOT / 'backend', check=False)
    cases = []
    if evidence.exists():
        for case in ET.parse(evidence).iter('testcase'):
            name = case.attrib['name']
            signed = '-True-' in name
            actual = '通过'
            if case.find('skipped') is not None: actual = '跳过，未验收'
            if case.find('failure') is not None or case.find('error') is not None: actual = '失败'
            cases.append({'case': name, 'expected': '签到后保留，释放零次' if signed else '仅释放本次一次，读回无该实例',
                          'actual': actual, 'evidence': str(evidence) + '#' + name})
    passed = completed.returncode == 0 and len(cases) == 9 and all(c['actual'] == '通过' for c in cases)
    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip())
    receipt = {'scope': '本地 HTTP fixture + 隔离 Redis；不代表真实预约或实机验收',
               'time': datetime.now(UTC).isoformat(), 'base_sha': sha, 'working_tree_dirty': dirty,
               'passed': passed, 'cases': cases}
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(str(output))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
