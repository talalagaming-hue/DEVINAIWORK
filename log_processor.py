import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DUMP_PATH = BASE_DIR / "test_data/raw_sys_dump.log"
BLOCK_PATTERN = re.compile(r"<(?P<tag>МОНОЛОГ|ЧАТ)>.*?</(?P=tag)>", re.DOTALL)


def extract_blocks(raw_dump: str) -> list[str]:
    return [match.group(0) for match in BLOCK_PATTERN.finditer(raw_dump)]


def main() -> None:
    raw_dump = DUMP_PATH.read_text(encoding="utf-8")
    blocks = extract_blocks(raw_dump)
    print("\n".join(blocks))


if __name__ == "__main__":
    main()
