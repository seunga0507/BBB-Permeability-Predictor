"""B3DB 분류 데이터셋 로딩 및 전처리.

출처/라이선스/label 정의는 data/raw/SOURCE.md 참고. 여기서는 임의의 값을 만들지 않고,
원본 파일에 있는 SMILES와 BBB+/BBB- 라벨만 사용한다.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from rdkit import RDLogger

from ml.standardize import standardize_smiles

RDLogger.DisableLog("rdApp.*")  # 손상된 SMILES에 대한 RDKit 경고를 조용히 처리

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "B3DB_classification.tsv"

LABEL_MAP = {"BBB+": 1, "BBB-": 0}


@dataclass
class CleaningReport:
    n_raw: int
    n_missing_smiles: int
    n_unparseable: int
    n_duplicate_conflicting: int
    n_duplicate_consistent_merged: int
    n_final: int


def load_and_clean(raw_path: Path = RAW_PATH) -> tuple[pd.DataFrame, CleaningReport]:
    """B3DB_classification.tsv를 읽어 SMILES 표준화 + 중복 제거까지 마친
    (canonical_smiles, label) 데이터프레임을 반환한다."""
    df = pd.read_csv(raw_path, sep="\t")
    n_raw = len(df)

    df = df[["SMILES", "BBB+/BBB-", "compound_name"]].rename(
        columns={"SMILES": "raw_smiles", "BBB+/BBB-": "raw_label"}
    )

    n_missing_smiles = df["raw_smiles"].isna().sum()
    df = df.dropna(subset=["raw_smiles"]).copy()

    df["label"] = df["raw_label"].map(LABEL_MAP)
    df["canonical_smiles"] = df["raw_smiles"].apply(standardize_smiles)

    n_before_parse_drop = len(df)
    df = df.dropna(subset=["canonical_smiles"]).copy()
    n_unparseable = n_before_parse_drop - len(df)

    # 같은 분자(canonical SMILES)가 라벨까지 같으면 하나만 남기고,
    # 같은 분자인데 라벨이 서로 다르면(출처 간 상충) 판단할 근거가 없으므로 모두 제거한다.
    label_counts = df.groupby("canonical_smiles")["label"].nunique()
    conflicting_smiles = set(label_counts[label_counts > 1].index)
    n_duplicate_conflicting = df["canonical_smiles"].isin(conflicting_smiles).sum()
    df = df[~df["canonical_smiles"].isin(conflicting_smiles)].copy()

    n_before_dedupe = len(df)
    df = df.drop_duplicates(subset=["canonical_smiles"]).reset_index(drop=True)
    n_duplicate_consistent_merged = n_before_dedupe - len(df)

    report = CleaningReport(
        n_raw=n_raw,
        n_missing_smiles=int(n_missing_smiles),
        n_unparseable=int(n_unparseable),
        n_duplicate_conflicting=int(n_duplicate_conflicting),
        n_duplicate_consistent_merged=int(n_duplicate_consistent_merged),
        n_final=len(df),
    )

    df["compound_name"] = df["compound_name"].fillna("(no name)")

    return df[["canonical_smiles", "label", "compound_name"]], report


if __name__ == "__main__":
    cleaned, report = load_and_clean()
    print(report)
    print(cleaned["label"].value_counts())
