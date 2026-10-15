"""B3DB 분류 데이터셋을 고정된 GitHub 커밋에서 재현 가능하게 내려받는다.

이미 data/raw/B3DB_classification.tsv 가 있고 체크섬이 일치하면 다시 받지 않는다.
자세한 출처는 data/raw/SOURCE.md 참고.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

# theochem/B3DB, tag v1.1.1
COMMIT_SHA = "75dab1cc607bb7a03f3de5c576cffd223e767844"
URL = (
    f"https://raw.githubusercontent.com/theochem/B3DB/{COMMIT_SHA}/"
    "B3DB/B3DB_classification.tsv"
)
EXPECTED_SHA256 = "47A160AEA1551423EAD2AAB70B301FB1646AEA03CF151FD614EB37C78FA55B82"

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "raw" / "B3DB_classification.tsv"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    if OUT_PATH.exists() and sha256_of(OUT_PATH) == EXPECTED_SHA256:
        print(f"이미 존재하고 체크섬이 일치합니다: {OUT_PATH}")
        return

    print(f"다운로드 중: {URL}")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(URL, OUT_PATH)

    actual = sha256_of(OUT_PATH)
    if actual != EXPECTED_SHA256:
        print(
            f"체크섬 불일치! expected={EXPECTED_SHA256} actual={actual}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"다운로드 완료 및 체크섬 확인: {OUT_PATH}")


if __name__ == "__main__":
    main()
