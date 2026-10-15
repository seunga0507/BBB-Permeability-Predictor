"""분자 표준화 (학습 데이터 정제와 추론 경로가 공유).

여러 fragment(염 등)로 이루어진 구조는 가장 큰 fragment만 남기고 sanitize한다.
ml/dataset.py(학습 데이터 정제)와 predictor.py(신규 화합물 추론) 양쪽에서 이 함수를
그대로 써서, 학습 때와 예측할 때 전처리가 어긋나는(train/serve skew) 일이 없게 한다.
"""

from rdkit import Chem


def standardize_mol(mol: Chem.Mol | None) -> Chem.Mol | None:
    if mol is None:
        return None

    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    if len(frags) > 1:
        mol = max(frags, key=lambda m: m.GetNumHeavyAtoms())

    try:
        Chem.SanitizeMol(mol)
    except Exception:
        return None

    if mol.GetNumHeavyAtoms() == 0:
        return None

    return mol


def standardize_smiles(raw_smiles: str) -> str | None:
    mol = standardize_mol(Chem.MolFromSmiles(raw_smiles))
    return Chem.MolToSmiles(mol) if mol is not None else None
