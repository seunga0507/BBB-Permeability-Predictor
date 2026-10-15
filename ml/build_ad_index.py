"""Applicability domain(AD)용 training fingerprint index를 만든다.

ml/train.py가 실제로 모델 학습에 사용한 것과 동일한 scaffold split의 **train set만**
사용한다 (valid/test는 모델이 실제로 "본" 데이터가 아니므로 AD 기준에서 제외).
scaffold_split은 결정적(deterministic)이라 ml/train.py를 다시 돌리지 않고도 동일한
train/valid/test 구성을 재현할 수 있다.

실행: (프로젝트 루트에서)
    venv\\Scripts\\python.exe -m ml.build_ad_index
"""

from pathlib import Path

import joblib
import numpy as np

from ml.dataset import load_and_clean
from ml.features import DESCRIPTOR_NAMES, featurize
from ml.scaffold_split import scaffold_split

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def main() -> None:
    cleaned, report = load_and_clean()
    print("Cleaning report:", report)

    X, _ = featurize(cleaned["canonical_smiles"])
    train_idx, _, _ = scaffold_split(cleaned["canonical_smiles"])

    fp_start = len(DESCRIPTOR_NAMES)
    train_fingerprints = (X[train_idx, fp_start:] > 0).astype(np.uint8)

    index = {
        "fingerprints": train_fingerprints,
        "smiles": cleaned["canonical_smiles"].to_numpy()[train_idx],
        "label": cleaned["label"].to_numpy()[train_idx],
        "compound_name": cleaned["compound_name"].to_numpy()[train_idx],
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / "ad_index.joblib"
    joblib.dump(index, out_path)
    print(f"Saved AD index ({train_fingerprints.shape[0]} compounds, "
          f"{train_fingerprints.shape[1]} bits) to {out_path}")


if __name__ == "__main__":
    main()
