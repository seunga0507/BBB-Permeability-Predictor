"""ChemDraw 스타일 MOL/SDF 업로드 -> BBB prediction pipeline 전체 테스트.

fixture는 tests/fixtures/generate_fixtures.py로 만들어졌고, ChemDraw가 실제로 만드는
MDL Molfile과 동일한 형식(2D 좌표 + wedge/hash 결합으로 표현된 stereochemistry,
M CHG 라인으로 표현된 formal charge)을 갖는다.

실행: (프로젝트 루트에서, 모델이 학습되어 있어야 함 — python -m ml.train, ml.build_ad_index)
    venv\\Scripts\\python.exe -m pytest tests\\test_pipeline.py -v
"""

import sys
from pathlib import Path

import pytest
from rdkit import Chem

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def upload_fixture(client, filename: str):
    path = FIXTURES_DIR / filename
    with open(path, "rb") as f:
        data = {"file": (f, filename)}
        resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    return resp


def assert_full_pipeline_ran(mol_result: dict):
    """descriptor 계산 -> fingerprint/model prediction -> applicability domain 까지
    전부 결과 dict에 채워졌는지 확인한다 (파이프라인이 끝까지 실행됐다는 증거)."""
    assert mol_result["valid"] is True
    assert set(mol_result["descriptors"].keys()) >= {
        "molecular_weight", "logp", "tpsa", "hbd", "hba", "rotatable_bonds",
    }
    assert mol_result["image_base64"]
    assert mol_result["predictions"], "모델별 예측(model prediction)이 비어 있음"
    for model_name, pred in mol_result["predictions"].items():
        assert "probability" in pred and "predicted_class" in pred
    assert mol_result["applicability_domain"] is not None, "applicability domain 결과가 없음"
    ad = mol_result["applicability_domain"]
    assert "max_similarity" in ad and "nearest_training_compounds" in ad
    assert len(ad["nearest_training_compounds"]) > 0


class TestChemDrawStyleMolUpload:
    def test_chiral_stereochemistry_preserved(self, client):
        resp = upload_fixture(client, "chemdraw_chiral.mol")
        assert resp.status_code == 200
        result = resp.get_json()["molecules"][0]
        assert_full_pipeline_ran(result)

        mol = Chem.MolFromSmiles(result["smiles"])
        assert mol is not None
        centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
        assert len(centers) == 1, f"stereocenter가 보존되지 않음: {result['smiles']}"
        assert centers[0][1] != "?", "stereocenter가 unassigned로 풀려버림"

    def test_formal_charge_preserved(self, client):
        resp = upload_fixture(client, "chemdraw_charged.mol")
        assert resp.status_code == 200
        result = resp.get_json()["molecules"][0]
        assert_full_pipeline_ran(result)

        mol = Chem.MolFromSmiles(result["smiles"])
        assert mol is not None
        charges = [atom.GetFormalCharge() for atom in mol.GetAtoms()]
        assert 1 in charges and -1 in charges, (
            f"zwitterion의 +1/-1 formal charge가 보존되지 않음: {result['smiles']}"
        )
        assert sum(charges) == 0

    def test_chiral_and_charged_together_preserved(self, client):
        resp = upload_fixture(client, "chemdraw_chiral_and_charged.mol")
        assert resp.status_code == 200
        result = resp.get_json()["molecules"][0]
        assert_full_pipeline_ran(result)

        mol = Chem.MolFromSmiles(result["smiles"])
        centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
        charges = [atom.GetFormalCharge() for atom in mol.GetAtoms()]
        assert len(centers) == 1 and centers[0][1] != "?"
        assert 1 in charges and -1 in charges

    def test_corrupted_mol_gives_clear_syntax_error(self, client):
        resp = upload_fixture(client, "corrupted.mol")
        assert resp.status_code == 200
        result = resp.get_json()["molecules"][0]
        assert result["valid"] is False
        assert result["error"]
        assert "구문" in result["error"]

    def test_bad_valence_mol_gives_clear_chemistry_error(self, client):
        resp = upload_fixture(client, "bad_valence.mol")
        assert resp.status_code == 200
        result = resp.get_json()["molecules"][0]
        assert result["valid"] is False
        assert result["error"]
        # 구문 오류가 아니라 valence(화학적 검증) 오류라는 걸 구분할 수 있어야 함
        assert "valence" in result["error"] or "sanitize" in result["error"].lower()

    def test_multi_record_sdf_mixed_valid_and_invalid(self, client):
        resp = upload_fixture(client, "chemdraw_multi.sdf")
        assert resp.status_code == 200
        molecules = resp.get_json()["molecules"]
        assert len(molecules) == 3

        valid_results = [m for m in molecules if m["valid"]]
        invalid_results = [m for m in molecules if not m["valid"]]
        assert len(valid_results) == 2, "정상 레코드 2개가 모두 처리돼야 함"
        assert len(invalid_results) == 1, "깨진 레코드 1개는 명확히 실패로 표시돼야 함"

        for result in valid_results:
            assert_full_pipeline_ran(result)

        assert invalid_results[0]["error"]


class TestSmilesInputStillWorks:
    """기존 SMILES 직접 입력 기능이 그대로 유지되는지 회귀 테스트."""

    def test_smiles_prediction_pipeline(self, client):
        resp = client.post(
            "/api/predict_smiles",
            json={"smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"},  # caffeine
        )
        assert resp.status_code == 200
        result = resp.get_json()["molecules"][0]
        assert_full_pipeline_ran(result)

    def test_invalid_smiles_gives_error(self, client):
        resp = client.post("/api/predict_smiles", json={"smiles": "not-a-smiles!!"})
        assert resp.status_code == 400
        assert resp.get_json()["error"]

    def test_empty_smiles_gives_error(self, client):
        resp = client.post("/api/predict_smiles", json={"smiles": ""})
        assert resp.status_code == 400
