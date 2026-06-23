from pathlib import Path


MAX_LINE_LENGTH = 120
ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    '.git',
    '.venv',
    '__pycache__',
    'migrations',
}


def iter_python_files():
    for path in ROOT.rglob('*.py'):
        if EXCLUDED_PARTS.intersection(path.parts):
            continue
        yield path


def main() -> int:
    violations = []
    for path in iter_python_files():
        for line_number, line in enumerate(
            path.read_text(encoding='utf-8').splitlines(),
            start=1,
        ):
            if len(line) > MAX_LINE_LENGTH:
                relative_path = path.relative_to(ROOT)
                violations.append(
                    f'{relative_path}:{line_number}: '
                    f'{len(line)} characters',
                )

    if violations:
        print('\n'.join(violations))
        return 1

    print(f'All Python lines are within {MAX_LINE_LENGTH} characters.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
