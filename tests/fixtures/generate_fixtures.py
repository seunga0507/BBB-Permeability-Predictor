"""ChemDraw가 실제로 만드는 것과 같은 형태(2D 좌표 + wedge/hash 결합으로 표현된
stereochemistry, M CHG 라인으로 표현된 formal charge)의 MOL/SDF 테스트 픽스처를 생성한다.

ChemDraw 자체가 이 환경에 없으므로, RDKit으로 stereochemistry/formal charge가 정의된
분자를 만들고 2D 좌표를 계산해 표준 MDL Molfile(V2000)로 저장한다. RDKit의
Chem.MolToMolFile은 2D 좌표 + 정의된 chiral tag가 있으면 wedge/hash 결합을 자동으로
써주므로, ChemDraw가 저장하는 MOL 파일과 구조적으로 동일한 형식이 된다.

재생성하려면: venv\\Scripts\\python.exe tests\\fixtures\\generate_fixtures.py
"""

from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

FIXTURES_DIR = Path(__file__).resolve().parent


def save_2d_molfile(smiles: str, name: str, filename: str) -> None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {smiles}")
    AllChem.Compute2DCoords(mol)
    mol.SetProp("_Name", name)
    Chem.MolToMolFile(mol, str(FIXTURES_DIR / filename))
    print(f"{filename}: {smiles} -> {Chem.MolToSmiles(mol)}")


# 1) 카이럴 화합물: (S)-alanine, 하나의 stereocenter -> wedge/hash 결합으로 표현됨
save_2d_molfile("C[C@@H](N)C(=O)O", "L-alanine", "chemdraw_chiral.mol")

# 2) 하전된 화합물(zwitterion): glycine zwitterion -> M CHG 라인으로 표현됨
save_2d_molfile("[NH3+]CC(=O)[O-]", "glycine zwitterion", "chemdraw_charged.mol")

# 3) 카이럴 + 하전이 동시에 있는 화합물: L-DOPA zwitterion
save_2d_molfile(
    "C1=CC(=C(C=C1C[C@@H]([NH3+])C(=O)[O-])O)O",
    "L-DOPA zwitterion",
    "chemdraw_chiral_and_charged.mol",
)

# 4) 문법 자체가 깨진 MOL 파일 (ChemDraw 저장 도중 파일이 잘리는 상황을 가정)
(FIXTURES_DIR / "corrupted.mol").write_text(
    "this is not a valid molfile at all\njust some garbage text\n", encoding="utf-8"
)

# 5) 구문은 정상이지만 화학적으로 불가능한 구조 (탄소 원자가 F 5개와 결합 = valence 초과)
bad_valence_molblock = """bad_valence
     manual           2D
  (구조는 정상 구문이지만 탄소 1개에 결합 5개 -> valence 초과로 sanitize 실패해야 함)
  6  5  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    0.0000    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0
   -1.0000    0.0000    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.0000    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.0000    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    1.0000    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  1  3  1  0
  1  4  1  0
  1  5  1  0
  1  6  1  0
M  END
"""
(FIXTURES_DIR / "bad_valence.mol").write_text(bad_valence_molblock, encoding="utf-8")

# 6) 여러 화합물이 들어있는 SDF: 정상 2개 + 구문 깨진 레코드 1개
alanine_block = Chem.MolToMolBlock(
    (lambda m: (AllChem.Compute2DCoords(m), m.SetProp("_Name", "L-alanine"), m)[-1])(
        Chem.MolFromSmiles("C[C@@H](N)C(=O)O")
    )
)
glycine_block = Chem.MolToMolBlock(
    (lambda m: (AllChem.Compute2DCoords(m), m.SetProp("_Name", "glycine zwitterion"), m)[-1])(
        Chem.MolFromSmiles("[NH3+]CC(=O)[O-]")
    )
)

sdf_content = (
    alanine_block.rstrip("\n") + "\n$$$$\n"
    + glycine_block.rstrip("\n") + "\n$$$$\n"
    + "broken record\n\n\ngarbage garbage garbage\n$$$$\n"
)
(FIXTURES_DIR / "chemdraw_multi.sdf").write_text(sdf_content, encoding="utf-8")

print("모든 fixture 생성 완료:", sorted(p.name for p in FIXTURES_DIR.glob("*.mol")))
print("SDF fixture:", (FIXTURES_DIR / "chemdraw_multi.sdf").name)
