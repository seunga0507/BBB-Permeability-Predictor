"""BBB permeability prediction 프로그램.

입력(ChemDraw 등에서 저장한 MOL/SDF 파일 업로드 또는 SMILES 직접 입력) 양쪽 모두 아래
동일한 파이프라인을 거친다:

    파일 업로드/SMILES 입력
    -> RDKit 구조 읽기 (parse_molecules / Chem.MolFromSmiles)
    -> 구조 검증 (sanitize, 실패 시 구체적 오류 메시지)
    -> descriptor 계산 (descriptors.calc_descriptors)
    -> fingerprint 계산 (ml.features.featurize_mol, predictor.predict 내부)
    -> model prediction (predictor.predict 내부, RF/XGBoost/SVM)
    -> applicability domain 평가 (predictor.predict 내부)
    -> 결과 표시 (build_molecule_result가 dict로 모아 JSON 응답)

training dataset에 없던 신규 구조도 동일한 경로로 예측한다. 여러 모델의 확률을 각각
보여줄 뿐, 이를 합친 단일 "최종 BBB score"는 만들지 않는다.
"""

import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, render_template, request, url_for
from rdkit import Chem

from descriptors import calc_descriptors, get_mol_name, mol_to_image_base64
from predictor import predict

ALLOWED_EXTENSIONS = {"mol", "sdf"}

# CAS 등록번호 형식: 2~7자리-2자리-1자리 (예: "659-40-5"). SMILES 입력란에 CAS
# 번호가 들어오면 SMILES로는 당연히 파싱이 안 되므로, 그 모양일 때만 PubChem에서
# SMILES를 조회해온다(일반 SMILES 입력 경로는 전혀 안 건드림 — 이 조회는 온전히
# fallback이라 인터넷 연결이 없어도 기존 SMILES/파일 업로드 기능은 그대로 동작한다).
CAS_NUMBER_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")


def resolve_cas_to_smiles(cas: str) -> str | None:
    """CAS 번호를 PubChem PUG REST API로 조회해서 isomeric SMILES를 반환한다.
    네트워크 오류/타임아웃/미등록 등 어떤 이유로든 실패하면 None을 반환한다
    (호출부에서 명확한 오류 메시지로 바꿔서 보여준다)."""
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{urllib.parse.quote(cas, safe='')}/property/IsomericSMILES/TXT"
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            text = resp.read().decode("utf-8").strip()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    first_line = text.splitlines()[0].strip() if text else ""
    return first_line or None


# SMILES 입력 줄 안에서 큰따옴표로 감싼 부분은 "이 부분구조를 반드시 포함해야
# 한다"는 표시다 — 따옴표를 떼어낸 전체 SMILES는 평소와 똑같이 그 분자 전체를
# 가리키고(따옴표 안쪽 텍스트는 분자 구조의 일부로 그대로 남는다, 지워지는 게
# 아니다), 따옴표 안의 텍스트만 별도로 꺼내서 SMARTS 부분구조 필터로 쓴다.
# 예: CC(C)NC"C(O)CO"c1ccc(CC(N)=O)cc1
#     -> 전체 분자: CC(C)NCC(O)COc1ccc(CC(N)=O)cc1 (아테놀올)
#     -> 필수 부분구조: C(O)CO
QUOTED_SUBSTRUCTURE_RE = re.compile(r'"([^"]+)"')


def extract_required_substructure(raw_line: str) -> tuple[str, str | None]:
    match = QUOTED_SUBSTRUCTURE_RE.search(raw_line)
    if not match:
        return raw_line, None
    inner = match.group(1).strip()
    clean_smiles = (raw_line[: match.start()] + match.group(1) + raw_line[match.end() :]).strip()
    return clean_smiles, (inner or None)


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB


@app.context_processor
def inject_static_version():
    """static/*.js, *.css 수정 시각을 쿼리스트링에 붙여, 개발 중 브라우저가 예전
    캐시된 파일을 계속 쓰는 문제(코드를 고쳤는데 화면엔 반영이 안 보이는 것)를 막는다."""

    def static_url(filename):
        path = Path(app.static_folder) / filename
        version = int(path.stat().st_mtime) if path.exists() else 0
        return url_for("static", filename=filename, v=version)

    return {"static_url": static_url}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _sanitize_with_reason(raw_mol: Chem.Mol) -> tuple[Chem.Mol | None, str | None]:
    """구문 분석은 됐지만 아직 sanitize 전인 Mol을 검증한다.

    ChemDraw MOL/SDF는 2D 좌표 + wedge/hash 결합으로 stereochemistry를, M CHG 라인으로
    formal charge를 표현하는데, 둘 다 sanitize 여부와 무관하게 구조를 읽는 시점(구문 분석
    단계)에서 이미 확정된다. 즉 sanitize=False로 먼저 읽고 나중에 SanitizeMol을 호출해도
    stereochemistry/formal charge는 sanitize=True로 한 번에 읽었을 때와 동일하게 보존된다.
    이렇게 2단계로 나누는 이유는 실패 사유(구문 오류 vs valence 등 화학적 오류)를 구분해서
    명확한 오류 메시지를 주기 위함이다.
    """
    try:
        Chem.SanitizeMol(raw_mol)
    except Exception as exc:
        return None, f"구조 검증(sanitize) 실패 — valence, 원자가 등을 확인하세요: {exc}"
    return raw_mol, None


def parse_molecules(filepath: str, ext: str) -> list[tuple[Chem.Mol | None, str | None]]:
    """MOL 파일은 분자 1개, SDF 파일은 분자 여러 개를 (mol, error_message) 튜플 리스트로 반환한다.

    성공하면 error_message는 None. 실패하면 mol은 None이고 error_message에 구체적인
    실패 사유(구문 오류인지 sanitize 실패인지)가 담긴다.
    """
    results: list[tuple[Chem.Mol | None, str | None]] = []

    if ext == "mol":
        raw_mol = Chem.MolFromMolFile(filepath, sanitize=False, strictParsing=False)
        if raw_mol is None:
            results.append((None, "MOL 파일 구문을 해석할 수 없습니다 (올바른 MDL Molfile인지 확인하세요)."))
        else:
            results.append(_sanitize_with_reason(raw_mol))
    else:
        supplier = Chem.SDMolSupplier(filepath, sanitize=False, strictParsing=False)
        for raw_mol in supplier:
            if raw_mol is None:
                results.append((None, "SDF 레코드 구문을 해석할 수 없습니다 (올바른 MDL SDfile인지 확인하세요)."))
            else:
                results.append(_sanitize_with_reason(raw_mol))

    return results


def build_molecule_result(
    mol: Chem.Mol | None,
    idx: int,
    fallback_name: str,
    parse_error: str | None = None,
    required_substructure_smarts: str | None = None,
) -> dict:
    """분자 하나 -> 화면에 표시할 결과 dict. 파이프라인 순서를 그대로 따른다:

    (읽기/검증은 호출 전에 이미 끝났다고 가정) -> descriptor 계산 -> fingerprint 계산 ->
    model prediction -> applicability domain -> 결과 dict 구성(화면 표시용).

    /api/upload(MOL/SDF)와 /api/predict_smiles(SMILES 직접 입력) 양쪽에서 공유한다.
    """
    if mol is None:
        return {
            "index": idx,
            "valid": False,
            "error": parse_error or "RDKit이 이 구조를 파싱하지 못했습니다 (구조 오류 가능).",
        }

    try:
        name = get_mol_name(mol, fallback=fallback_name)
        # descriptor 계산 (화면 표시용, 원래 구조 그대로)
        descriptors = calc_descriptors(mol)
        # static/style.css의 .detail-image 표시 박스(460x240)와 같은 비율로 렌더링해서
        # object-fit:contain으로 인한 빈 여백(레터박스)을 없앤다.
        image_base64 = mol_to_image_base64(mol, size=(460, 240))
        # fingerprint 계산 + model prediction + applicability domain
        # (predictor.predict 내부에서 표준화 -> descriptor/fingerprint -> 모델별 예측 ->
        #  AD 평가 순서로 수행된다. 자세한 내용은 predictor.py 참고)
        bbb = predict(mol, required_substructure_smarts=required_substructure_smarts)
        ad = bbb["applicability_domain"]
        identified_name = ad.get("identified_name") if ad else None
        # 파일/입력에 이미 실제 이름이 있으면 그걸 존중하고, 없을 때만(fallback 그대로일 때만)
        # training 데이터에서 식별된 이름으로 대체한다.
        if identified_name and name == fallback_name:
            name = identified_name
        return {
            "index": idx,
            "valid": True,
            "name": name,
            "identified_name": identified_name,
            "smiles": Chem.MolToSmiles(mol),
            "descriptors": descriptors,
            "image_base64": image_base64,
            "predictions": bbb["predictions"],
            "applicability_domain": bbb["applicability_domain"],
            "prediction_mode": bbb["prediction_mode"],
            "read_across_reason": bbb.get("read_across_reason"),
            "read_across_detail": bbb.get("read_across_detail"),
            "retrain_info": bbb.get("retrain_info"),
            "global_predictions": bbb.get("global_predictions"),
        }
    except Exception as exc:
        return {
            "index": idx,
            "valid": False,
            "error": f"descriptor/예측 계산 중 오류: {exc}",
        }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "파일이 선택되지 않았습니다."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "MOL 또는 SDF 파일만 업로드할 수 있습니다."}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()

    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        parsed = parse_molecules(tmp_path, ext)
    except Exception as exc:
        return jsonify({"error": f"파일을 읽는 중 오류가 발생했습니다: {exc}"}), 400
    finally:
        os.unlink(tmp_path)

    if not parsed:
        return jsonify({"error": "구조를 찾을 수 없습니다."}), 400

    results = [
        build_molecule_result(mol, idx, fallback_name=f"molecule_{idx + 1}", parse_error=err)
        for idx, (mol, err) in enumerate(parsed)
    ]

    return jsonify({"molecules": results})


@app.route("/api/structure_image")
def structure_image():
    """Training 화합물 이름을 클릭했을 때 그 화합물의 등록된 구조를 보여주기 위한
    엔드포인트. 예측 응답에는 매번 5개씩 이미지를 다 실어보내지 않고, 사용자가 실제로
    클릭했을 때만 그때그때 렌더링한다."""
    smiles = (request.args.get("smiles") or "").strip()
    if not smiles:
        return jsonify({"error": "SMILES가 없습니다."}), 400

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return jsonify({"error": f"RDKit이 이 SMILES를 파싱하지 못했습니다: {smiles}"}), 400

    return jsonify({
        "image_base64": mol_to_image_base64(mol),
        "molecular_weight": calc_descriptors(mol)["molecular_weight"],
    })


@app.route("/api/predict_smiles", methods=["POST"])
def predict_smiles():
    """SMILES 한 줄 또는 여러 줄(화합물별 한 줄씩) 입력을 모두 처리한다."""
    data = request.get_json(silent=True) or {}
    raw = (data.get("smiles") or "").strip()

    if not raw:
        return jsonify({"error": "SMILES를 입력하세요."}), 400

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return jsonify({"error": "SMILES를 입력하세요."}), 400

    results = []
    for idx, original_line in enumerate(lines):
        raw_line, required_substructure = extract_required_substructure(original_line)
        smiles = raw_line
        mol = Chem.MolFromSmiles(smiles)

        if mol is None and CAS_NUMBER_RE.match(raw_line):
            resolved_smiles = resolve_cas_to_smiles(raw_line)
            if resolved_smiles is None:
                results.append({
                    "index": idx,
                    "valid": False,
                    "error": f"CAS 번호 '{raw_line}'를 PubChem에서 찾지 못했습니다 "
                             f"(등록되지 않은 번호이거나 인터넷 연결을 확인하세요).",
                })
                continue
            smiles = resolved_smiles
            mol = Chem.MolFromSmiles(smiles)

        if mol is None:
            results.append({
                "index": idx,
                "valid": False,
                "error": f"RDKit이 이 SMILES를 파싱하지 못했습니다: {smiles}",
            })
            continue
        results.append(build_molecule_result(
            mol, idx, fallback_name=raw_line, required_substructure_smarts=required_substructure
        ))

    return jsonify({"molecules": results})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
