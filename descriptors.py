"""RDKit 기반 구조 파싱, descriptor 계산, 2D 이미지 생성 유틸리티."""

import base64

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors
from rdkit.Chem.Draw import rdMolDraw2D


def calc_descriptors(mol: Chem.Mol) -> dict:
    """주요 QSAR/약물유사성 descriptor를 계산한다."""
    return {
        "molecular_weight": round(Descriptors.MolWt(mol), 2),
        "logp": round(Crippen.MolLogP(mol), 2),
        "tpsa": round(Descriptors.TPSA(mol), 2),
        "hbd": Descriptors.NumHDonors(mol),
        "hba": Descriptors.NumHAcceptors(mol),
        "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
        "num_rings": Descriptors.RingCount(mol),
        "num_atoms": mol.GetNumAtoms(),
    }


def mol_to_image_base64(mol: Chem.Mol, size=(350, 300)) -> str:
    """2D 구조 이미지를 PNG로 렌더링하고 base64 문자열로 반환한다.

    Draw.MolToImage는 분자 크기와 무관하게 항상 캔버스(size)를 꽉 채우도록
    자동으로 확대/축소한다 — 그래서 원자 몇 개짜리 작은 분자도 큰 분자와 똑같이
    커 보였다. 대신 결합 하나의 픽셀 길이(fixedBondLength)를 고정해서 그리면,
    실제 분자 크기에 비례해서 작은 분자는 작게, 큰 분자는 크게(캔버스 안에서
    가운데 정렬되어) 표시된다."""
    drawer = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
    drawer.drawOptions().fixedBondLength = 35
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
    drawer.FinishDrawing()
    return base64.b64encode(drawer.GetDrawingText()).decode("ascii")


def get_mol_name(mol: Chem.Mol, fallback: str) -> str:
    """MOL/SDF에 이름(_Name) property가 있으면 사용하고, 없으면 fallback 사용."""
    if mol.HasProp("_Name") and mol.GetProp("_Name").strip():
        return mol.GetProp("_Name").strip()
    return fallback
