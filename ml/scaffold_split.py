"""Bemis-Murcko scaffold 기반 train/validation/test split.

MoleculeNet(Wu et al., 2018, "MoleculeNet: a benchmark for molecular machine learning")에서
쓰인 것과 같은 방식: 분자를 scaffold별로 묶고, 큰 scaffold 그룹부터 순서대로
train -> valid -> test 에 채워 넣는다. 이렇게 하면 같은(또는 매우 비슷한) 골격을 가진
분자가 train과 test에 동시에 들어가는 걸 막아서, random split보다 더 현실적인
(더 어려운) 일반화 성능 평가가 된다.
"""

from collections import defaultdict

import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold


def _scaffold_smiles(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    scaffold = MurckoScaffold.GetScaffoldForMol(mol)
    scaffold_smi = Chem.MolToSmiles(scaffold)
    return scaffold_smi if scaffold_smi else smiles  # scaffold가 없는 분자는 자기 자신을 키로 사용


def scaffold_split(
    smiles: pd.Series,
    frac_train: float = 0.8,
    frac_valid: float = 0.1,
    frac_test: float = 0.1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    assert abs(frac_train + frac_valid + frac_test - 1.0) < 1e-8

    scaffold_to_indices = defaultdict(list)
    for idx, smi in enumerate(smiles):
        scaffold_to_indices[_scaffold_smiles(smi)].append(idx)

    scaffold_groups = sorted(scaffold_to_indices.values(), key=len, reverse=True)

    n_total = len(smiles)
    n_train_cutoff = int(frac_train * n_total)
    n_valid_cutoff = int((frac_train + frac_valid) * n_total)

    train_idx, valid_idx, test_idx = [], [], []
    for group in scaffold_groups:
        if len(train_idx) + len(group) <= n_train_cutoff:
            train_idx.extend(group)
        elif len(train_idx) + len(valid_idx) + len(group) <= n_valid_cutoff:
            valid_idx.extend(group)
        else:
            test_idx.extend(group)

    return np.array(train_idx), np.array(valid_idx), np.array(test_idx)


def random_split(
    n_total: int,
    frac_train: float = 0.8,
    frac_valid: float = 0.1,
    frac_test: float = 0.1,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """scaffold split과 비교하기 위한 단순 random split (baseline 비교용)."""
    assert abs(frac_train + frac_valid + frac_test - 1.0) < 1e-8

    rng = np.random.RandomState(seed)
    indices = rng.permutation(n_total)

    n_train_cutoff = int(frac_train * n_total)
    n_valid_cutoff = int((frac_train + frac_valid) * n_total)

    return (
        indices[:n_train_cutoff],
        indices[n_train_cutoff:n_valid_cutoff],
        indices[n_valid_cutoff:],
    )
