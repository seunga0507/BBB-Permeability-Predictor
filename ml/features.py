"""QSAR baseline featurization: RDKit descriptor 벡터 + Morgan fingerprint.

앱(descriptors.py)에서 화면에 보여주는 descriptor 계산과는 별개로, 여기서는
모델 입력 feature 행렬을 만드는 데 집중한다.
"""

import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors
from rdkit.Chem import rdFingerprintGenerator

DESCRIPTOR_NAMES = [
    "molecular_weight",
    "logp",
    "tpsa",
    "hbd",
    "hba",
    "rotatable_bonds",
    "num_rings",
    "num_aromatic_rings",
    "num_heteroatoms",
    "fraction_csp3",
]

FP_RADIUS = 2
FP_N_BITS = 2048

# includeChirality=True: R/S 입체이성질체가 서로 다른 fingerprint를 갖도록 한다.
# 입체 정보가 없는(SMILES에 @ 표기가 없는) 화합물은 이 옵션과 무관하게 이전과
# 동일한 fingerprint가 나오므로, 대다수 achiral 학습 데이터의 feature는 그대로 유지된다.
_fp_generator = rdFingerprintGenerator.GetMorganGenerator(
    radius=FP_RADIUS, fpSize=FP_N_BITS, includeChirality=True
)


def _descriptor_vector(mol: Chem.Mol) -> list[float]:
    return [
        Descriptors.MolWt(mol),
        Crippen.MolLogP(mol),
        Descriptors.TPSA(mol),
        Descriptors.NumHDonors(mol),
        Descriptors.NumHAcceptors(mol),
        Descriptors.NumRotatableBonds(mol),
        Descriptors.RingCount(mol),
        Descriptors.NumAromaticRings(mol),
        Descriptors.NumHeteroatoms(mol),
        Descriptors.FractionCSP3(mol),
    ]


def fingerprint_bits(mol: Chem.Mol) -> np.ndarray:
    """Morgan fingerprint를 0/1 numpy 벡터로 반환한다 (applicability domain의
    Tanimoto 유사도 계산에도 재사용됨)."""
    fp = _fp_generator.GetFingerprintAsNumPy(mol)
    return fp.astype(np.float32)


def feature_names() -> list[str]:
    return list(DESCRIPTOR_NAMES) + [f"fp_bit_{i}" for i in range(FP_N_BITS)]


def featurize_mol(mol: Chem.Mol) -> np.ndarray:
    """이미 파싱/sanitize된 RDKit Mol 하나 -> feature 벡터 1개.

    학습 파이프라인(featurize)과 추론 경로(predictor.py) 양쪽에서 이 함수를 공유해서
    feature 계산 로직이 어긋나지 않게 한다.
    """
    desc = _descriptor_vector(mol)
    fp = fingerprint_bits(mol)
    return np.concatenate([np.array(desc, dtype=np.float32), fp])


def featurize(smiles_list: pd.Series) -> tuple[np.ndarray, list[str]]:
    """canonical SMILES 목록 -> (descriptor + Morgan fingerprint) 결합 feature 행렬.

    이 시점의 SMILES는 이미 ml.dataset.load_and_clean에서 검증되었다고 가정한다.
    """
    rows = [featurize_mol(Chem.MolFromSmiles(smi)) for smi in smiles_list]
    return np.vstack(rows), feature_names()
