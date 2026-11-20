"""Create a fresh isolated sketch and embed the Chinese dashboard there."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    chinese = project / 'zh-CN/dashboard_source.zh-CN.html'
    if not chinese.is_file():
        raise SystemExit(f'Missing Chinese dashboard: {chinese}')
    sketches = list(project.glob('*.ino'))
    if len(sketches) != 1:
        raise SystemExit('Expected exactly one root .ino file')
    excluded = {args.output_root.resolve(), (project / 'Final-Build').resolve()}

    def ignore(directory, names):
        return [name for name in names if name in {
            '.git', 'build', 'build_variants', 'Final-Build', '__pycache__', '.pio'
        } or (Path(directory) / name).resolve() in excluded]

    args.destination.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='zh-CN-', dir=args.destination.resolve()))
    sketch = work / sketches[0].stem
    shutil.copytree(project, sketch, ignore=ignore)
    shutil.copyfile(chinese, sketch / 'dashboard_source.html')
    subprocess.run([sys.executable, str(sketch / 'tools/build_dashboard.py')],
                   check=True, stdout=subprocess.DEVNULL)
    print(sketch)


if __name__ == '__main__':
    main()
