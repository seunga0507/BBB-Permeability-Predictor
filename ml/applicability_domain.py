"""Fingerprint 유사도 기반 applicability domain(AD) 평가.

모델이 실제로 학습에 사용한 training 화합물들(ml/build_ad_index.py로 만든
ml/artifacts/ad_index.joblib)의 Morgan fingerprint와 질의 화합물의 fingerprint 간
Tanimoto 유사도를 계산해서:
  - 가장 가까운 training 화합물들(및 그 실험/문헌 라벨)을 찾아 보여주고,
  - 최근접 유사도가 임계값보다 낮으면 "training chemical space를 벗어났다"고 보고
    prediction의 confidence를 낮춘다.

임계값(기본 0.4, ECFP4/Morgan radius=2 기준 Tanimoto)은 QSAR/read-across 문헌에서
"구조적으로 유사하다"고 볼 때 흔히 쓰이는 휴리스틱 값이며, 이 프로젝트의 데이터셋에 대해
별도로 통계적으로 최적화한 값은 아니다. 필요하면 검증 데이터로 재조정할 수 있다.
"""

import re
from pathlib import Path

import joblib
import numpy as np
from rdkit import Chem

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
AD_INDEX_PATH = ARTIFACTS_DIR / "ad_index.joblib"

DEFAULT_SIMILARITY_THRESHOLD = 0.4
TOP_K = 5

# 필수 Moiety(SMARTS) 필터를 걸었을 때, 매칭된 training 화합물만으로 RF/XGBoost/SVM을
# 즉석 재학습해서 예측할지(subset retrain), 아니면 그 화합물들의 실험 라벨을 유사도로
# 가중 평균해서 보여줄지(read-across)를 가르는 기준. 매칭 개수가 너무 적거나 한쪽
# 라벨(BBB+/BBB-)로 치우쳐 있으면 분류기 학습 자체가 불안정하거나(과적합/암기) 아예
# fit() 단계에서 에러가 나므로(예: SVM은 클래스가 1개뿐이면 학습 자체가 불가능), 그런
# 경우엔 read-across로 대체한다.
READ_ACROSS_MIN_TOTAL = 30
READ_ACROSS_MIN_PER_CLASS = 5

# 신뢰도(%) 계산 방식: 가장 가까운 화합물이 이 값 이상이면 그 화합물 1개만으로 신뢰도를
# 매기고(단일 거의-동일 매치는 그 자체로 강한 근거), 그 정도로 가까운 화합물이 하나도
# 없으면(단일 매치 하나만으로는 우연/오류 가능성이 있으므로) 가장 가까운 3개의 평균으로
# 좀 더 보수적으로 판단한다.
EXACT_MATCH_THRESHOLD = 0.99
TOP_N_FOR_AVERAGE = 3

LOW_CONFIDENCE_LABEL = "Low confidence / Outside applicability domain"

# ml/dataset.py가 이름 없는 화합물에 채워넣는 placeholder들 + 원본 데이터의 "-" 표기.
# 이 값들은 "실제로 식별된 이름"으로 취급하지 않는다.
UNNAMED_VALUES = {"", "-", "(no name)"}

# B3DB 원본 데이터 자체에 실제 화합물명 대신 CAS 등록번호가 compound_name 칸에
# 잘못 들어간 행이 7,807개 중 168개 있다(예: 카페인 행의 이름이 "Caffeine"이
# 아니라 "58-08-2"). 원본 파일(data/raw/B3DB_classification.tsv)은 해시까지 박아둔
# 그대로의 3rd-party 데이터라 직접 고치지 않고, 표시 단계에서 "실제 이름이 아님"으로
# 취급해서 다른 placeholder들과 똑같이 "Unknown"으로 보여준다.
_CAS_NUMBER_LIKE_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

# B3DB 원본 데이터에는 compound_name은 그대로인데 SMILES가 실제 그 화합물과
# 분자식부터 다른("이름-구조 불일치") 행도 섞여 있다. 예:
#   - "atenolol" 행인데 SMILES에 CH2가 하나 빠져 있거나(C13H20N2O3, 실제는
#     C14H22N2O3), 아예 전혀 다른 설폰아미드계 구조(C17H17NO2S2)인 경우
#   - "cefazolin" 행인데 실제 cefazolin과 무관한 구조(멘톨 에스터, 이미다졸
#     항진균제 골격 등)인 경우
# 사용자가 화합물명을 클릭해 구조를 봤을 때 실제로는 그 화합물이 아닌 걸
# 보여주면 오해를 주므로, 직접 SMILES를 대조해 발견한 이런 행들은 (구조는
# training set에서 유사도 비교용으로 그대로 쓰되) 이름만 CAS-번호 오표기와
# 같은 방식으로 "실제 이름 아님" 취급해서 "Unknown"으로 표시한다. 원본 TSV는
# 해시로 고정된 3rd-party 데이터라 고치지 않는다 — 표시 단계에서만 가린다.
#
# 여기 담긴 SMILES는 원본 TSV에 적힌 그대로의 문자열이어야 매칭된다(표준화
# 전 원본 표기 기준).
_NAME_STRUCTURE_MISMATCH_SMILES = {
    "CC(C)NC(O)COc1ccc(CC(N)=O)cc1",  # "atenolol"으로 표기되어 있으나 CH2 하나가 빠진 구조
    "Cc1ccc(S(=O)(=O)[C@H]2[C@H](C(N)=S)[C@@H]2c2ccccc2)cc1",  # "atenolol"과 무관한 설폰아미드계 구조
    "CC(C)[C@@H]1CC[C@@H](C)C[C@@H]1OC(=O)Cn1nc(-c2ccco2)oc1=O",  # "cefazolin"과 무관한 구조
    "CC(=O)N1CCN(c2ccc(OCC3COC(Cn4ccnc4)(c4ccc(Cl)cc4Cl)O3)cc2)CC1",  # "cefazolin"과 무관한 구조
    "COC(=O)C[C@H](c1cccnc1)c1c(O)c(C(=O)OC)c[nH]c1=O",  # "caffeine"으로 표기되어 있으나 실제 카페인과 무관한 구조(C16H16N2O6, 실제는 C8H10N4O2)
}

# 반대 경우: 실제로는 정확히 그 화합물의 구조인데 compound_name 칸에 CAS 번호만
# 들어 있는 행들 중, 화학적으로 명백히 신원을 확정할 수 있는 것들은 "Unknown"으로
# 숨기지만 말고 올바른 이름을 직접 붙여준다(예: 카페인 — 이 SMILES는 실제
# 카페인의 정확한 구조와 일치하는데 이름 칸은 "58-08-2"였다). 여기 담긴 SMILES도
# 원본 TSV에 적힌 그대로의 문자열이어야 매칭된다.
_KNOWN_NAME_CORRECTIONS = {
    "Cn1c(=O)c2c(ncn2C)n(C)c1=O": "Caffeine",
}


def _is_real_name(name: str, smiles: str | None = None) -> bool:
    name = name.strip()
    if name in UNNAMED_VALUES:
        return False
    if _CAS_NUMBER_LIKE_RE.match(name):
        return False
    if smiles is not None and smiles.strip() in _NAME_STRUCTURE_MISMATCH_SMILES:
        return False
    return True


def _load_index():
    if not AD_INDEX_PATH.exists():
        return None
    return joblib.load(AD_INDEX_PATH)


_INDEX = _load_index()


def ad_index_available() -> bool:
    return _INDEX is not None


def _build_training_mol_cache():
    """부분구조(SMARTS) 필터링을 빠르게 하려고, training 화합물 6천여 개를 요청마다
    다시 파싱하지 않고 모듈 로드 시 한 번만 RDKit Mol로 미리 만들어 캐시해둔다."""
    if _INDEX is None:
        return None
    return [Chem.MolFromSmiles(str(smi)) for smi in _INDEX["smiles"]]


_TRAINING_MOLS = _build_training_mol_cache()


def match_substructure_candidates(required_substructure_smarts: str) -> "np.ndarray | None":
    """필수 Moiety(SMARTS)를 실제로 포함하는 training 화합물들의 인덱스 배열.

    assess()가 내부적으로 하는 것과 동일한 필터링이며, predictor.py가 "매칭된
    화합물만으로 즉석 재학습(subset retrain)"할지 "read-across"로 보여줄지를
    고를 때 전체 매칭 개수/클래스 분포를 미리 알기 위해 쓴다. SMARTS 파싱에
    실패하면 None을 반환한다(assess()의 substructure_error와 같은 판단 기준).
    """
    if _INDEX is None or not required_substructure_smarts:
        return None
    pattern = Chem.MolFromSmarts(required_substructure_smarts)
    if pattern is None:
        return None
    matches = np.array([
        mol is not None and mol.HasSubstructMatch(pattern)
        for mol in _TRAINING_MOLS
    ])
    return np.where(matches)[0]


def candidate_class_balance(candidate_idx: np.ndarray) -> tuple[int, int]:
    """candidate_idx(match_substructure_candidates의 결과)에 해당하는 training
    화합물들 중 BBB+/BBB- 개수. (n_positive, n_negative)."""
    labels = _INDEX["label"][candidate_idx]
    return int((labels == 1).sum()), int((labels == 0).sum())


def candidate_training_subset(candidate_idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """candidate_idx에 해당하는 training 화합물들의 (SMILES, label) 배열 — 그
    부분집합만으로 모델을 즉석 재학습할 때 feature를 새로 계산하는 데 쓴다."""
    return _INDEX["smiles"][candidate_idx], _INDEX["label"][candidate_idx]


_STEREO_PREFIX_WORDS = {
    "d", "l", "dl", "r", "s", "rs", "meso", "cis", "trans", "n", "iso", "sec", "tert", "rac",
}

# "dl"/"rs"는 D형과 L형(또는 R형과 S형)이 섞인 라세믹을 뜻하는 약어 자체이므로,
# 앞글자만 대문자화하는 일반 규칙과 달리 관례대로 두 글자 다 대문자로 쓴다(DL-, RS-).
_FULL_UPPER_PREFIX_WORDS = {"dl", "rs"}


def _title_case(name: str) -> str:
    """첫 단어의 맨 앞 글자만 대문자로 바꾸되, D-/L-/R-/S-/meso-/cis- 같은 입체/이성질체
    접두사 뒤에 하이픈으로 바로 이어지는 부분은 그것도 첫 글자를 대문자로 바꾼다
    ("d-mannitol" -> "D-Mannitol"). 그 외 하이픈 뒤 부분(숫자 locant 뒤에 오는 일반
    명명 부분 등)은 건드리지 않는다("2-methylpropan-1-ol" -> "2-Methylpropan-1-ol",
    "-Ol"로 만들지 않음). 공백으로 구분된 두 번째 단어부터도 건드리지 않는다
    ("lactic acid" -> "Lactic acid")."""
    first_word, sep, rest = name.partition(" ")

    tokens = re.split(r"(-)", first_word)
    out = []
    capitalize_next = True
    for tok in tokens:
        if tok == "-":
            out.append(tok)
            continue
        core = re.sub(r"[^A-Za-z]", "", tok).lower()
        if not core:
            out.append(tok)
            continue
        if capitalize_next:
            if core in _FULL_UPPER_PREFIX_WORDS:
                tok = re.sub(r"[A-Za-z]+", lambda m: m.group(0).upper(), tok)
            else:
                tok = re.sub(r"[A-Za-z]", lambda m: m.group(0).upper(), tok, count=1)
        out.append(tok)
        capitalize_next = core in _STEREO_PREFIX_WORDS

    return "".join(out) + sep + rest


def _display_name(raw_name: str, smiles: str | None = None) -> str:
    """placeholder 값("-"/빈 문자열/"(no name)"), CAS 번호가 잘못 들어간 경우,
    그리고 이름-구조가 불일치하는 것으로 확인된 경우까지 전부 "Unknown"으로
    통일하고, 실제 이름이면 단어별 첫 글자를 대문자로 정리한다. 수동으로 확인된
    이름 보정(_KNOWN_NAME_CORRECTIONS)이 있으면 그걸 최우선으로 쓴다."""
    if smiles is not None and smiles.strip() in _KNOWN_NAME_CORRECTIONS:
        return _KNOWN_NAME_CORRECTIONS[smiles.strip()]
    name = raw_name.strip()
    if not _is_real_name(name, smiles):
        return "Unknown"
    return _title_case(name)


_STEREO_MARKER_RE = re.compile(r"\(\s*[rs](\s*,\s*[rs])*\s*\)", re.IGNORECASE)

# 입체화학을 "주장"하는 접두사만 여기 포함한다 — n-/iso-/sec-/tert- 같은 건
# 입체 표기가 아니라 사슬/분기 구조를 가리키는 이름 관용구라서 대상이 아니다.
_STEREO_CLAIM_WORDS = {"d", "l", "dl", "r", "s", "rs", "meso", "cis", "trans", "rac"}


def _strip_stereo_prefix_token(word: str) -> str | None:
    """word가 "D-mannitol"처럼 입체 접두사로 시작하면 접두사를 뗀 나머지(첫 글자
    대문자로)를 반환하고, 아니면 None을 반환한다."""
    prefix, dash, remainder = word.partition("-")
    if not dash or not remainder:
        return None
    prefix_core = re.sub(r"[^A-Za-z]", "", prefix).lower()
    if prefix_core not in _STEREO_CLAIM_WORDS:
        return None
    return remainder[0].upper() + remainder[1:]


def _strip_unconfirmed_stereo_prefix(name: str) -> str:
    """이름에 붙은 입체 접두사(D-/L-/DL-/R-/S-/RS-/cis-/trans-/meso-/rac-)가 실제로는
    SMILES에서 확인되지 않았을 때(입체중심이 정의되지 않음) 제거한다. "D-Mannitol
    (입체정보 없음)"처럼 이름과 뒤에 붙는 안내 문구가 서로 모순되는 것을 막기 위함 —
    구조로 확인되지 않은 D/L/R/S 표기를 이름에만 남겨두지 않는다.
    맨 앞 단어("D-mannitol ...")뿐 아니라, "Mannitol (D-mannitol)"처럼 뒤에 동의어로
    괄호 안에 딸려 오는 경우도 확인해서 뗀다 — 접두사를 떼고 나면 본 이름과 완전히
    같아지는(즉 괄호가 그 표기 하나 때문에만 붙어 있던) 경우는 괄호째로 없앤다."""
    first_word, sep, rest = name.partition(" ")
    stripped_first = _strip_stereo_prefix_token(first_word)
    if stripped_first is not None:
        name = stripped_first + sep + rest

    match = re.match(r"^(.*\S)\s\(([^()]*)\)\s*$", name)
    if match:
        main_part, paren_part = match.group(1), match.group(2)
        stripped_paren = _strip_stereo_prefix_token(paren_part)
        if stripped_paren is not None:
            if stripped_paren.strip().lower() == main_part.strip().lower():
                name = main_part  # 접두사만 떼면 본 이름과 같아지는 중복 동의어 -> 통째로 제거
            else:
                name = f"{main_part} ({stripped_paren})"

    return name


def _name_with_cip(name: str, smiles: str) -> str:
    """이름 뒤에 입체화학 상태 표기를 붙인다:
      - 입체중심이 전부 정의돼 있으면 " (R)" / " (R,S)" 같은 실제 CIP 코드
      - 입체중심이 있을 수 있는데(카이랄 가능 구조인데) SMILES에 정의가 안 돼 있으면
        " (입체정보 없음)" — 이름이 "D-Mannitol"이라고 주장해도 SMILES 자체엔 그 근거가
        없는 경우를 놓치지 않기 위함(이름과 실제 구조가 어긋나는 문제, atenolol/mannitol
        사례에서 확인됨).
      - 애초에 입체중심이 존재할 수 없는(카이랄 불가능한) 구조면 아무것도 안 붙인다.
    이름에 이미 "(R)"/"(S)"류 표기가 있으면(예: "(S)-Metoprolol") 정의된 CIP 코드는
    중복으로 덧붙이지 않는다.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return name

    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=False)
    if not centers:
        return name  # 카이랄 중심 자체가 없는 구조 -> 표기할 게 없음

    assigned = [code for _, code in centers if code in ("R", "S")]
    n_unassigned = sum(1 for _, code in centers if code not in ("R", "S"))

    if not assigned and n_unassigned:
        name = _strip_unconfirmed_stereo_prefix(name)
        return f"{name} (입체정보 없음)"
    if assigned and n_unassigned:
        # 일부만 정의됐어도, 이름의 D/L/R/S 접두사는 보통 분자 전체의 입체배치를
        # 주장하는 것이라 "일부만 확인됨" 상태와는 여전히 어긋난다 — 마찬가지로 뗀다.
        name = _strip_unconfirmed_stereo_prefix(name)
        return f"{name} ({','.join(assigned)} 일부 + 입체정보 없음 {n_unassigned}곳)"
    # 전부 정의됨
    if _STEREO_MARKER_RE.search(name):
        return name
    return f"{name} ({','.join(assigned)})"


def _tanimoto(query_bits: np.ndarray, train_bits: np.ndarray) -> np.ndarray:
    """query_bits: (n_bits,) 0/1 벡터. train_bits: (n_train, n_bits) 0/1 행렬."""
    query = query_bits.astype(np.float32)
    train = train_bits.astype(np.float32)
    intersection = train @ query
    union = query.sum() + train.sum(axis=1) - intersection
    union = np.where(union == 0, 1.0, union)  # 둘 다 빈 fingerprint인 경우 0-division 방지
    return intersection / union


def assess(
    query_fingerprint: np.ndarray,
    query_smiles: str | None = None,
    top_k: int = TOP_K,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    required_substructure_smarts: str | None = None,
) -> dict | None:
    """질의 화합물의 fingerprint -> AD 평가 결과. training index가 없으면 None.

    query_smiles(표준화된 canonical SMILES, predictor.py와 ml/dataset.py가 공유하는
    ml/standardize.py 기준)가 training index의 canonical SMILES와 정확히 일치하면,
    그 화합물의 이름을 "identified_name"으로 함께 반환한다(이름이 없는 placeholder
    화합물은 제외). fingerprint 유사도만으로는 서로 다른 구조가 우연히 같은 fingerprint를
    가질 가능성이 있으므로, "식별"은 fingerprint가 아니라 canonical SMILES 문자열의
    완전 일치로만 판단한다.

    required_substructure_smarts가 주어지면, "가장 가까운 training 화합물" 탐색을
    그 부분구조를 실제로 포함하는(SMARTS 부분구조 매칭) training 화합물로만 제한한다.
    Tanimoto 유사도("전체 대비 비율")와 달리 "이 조각이 있냐 없냐"만 보는 하드
    필터라서, 나머지 구조가 달라도 걸러낼 수 있다. SMARTS 파싱에 실패하면
    substructure_error에 이유를 담아 돌려주고(필터는 적용하지 않음), 필터를 통과하는
    training 화합물이 하나도 없으면 nearest_training_compounds가 빈 리스트로 온다.
    """
    if _INDEX is None:
        return None

    candidate_idx = np.arange(_INDEX["fingerprints"].shape[0])
    substructure_error = None
    substructure_match_count = None

    if required_substructure_smarts:
        pattern = Chem.MolFromSmarts(required_substructure_smarts)
        if pattern is None:
            substructure_error = (
                f"'{required_substructure_smarts}'를 필수 Moiety 패턴(SMARTS)으로 해석하지 "
                f"못했습니다 — 필터 없이 전체 training 화합물 기준으로 보여줍니다."
            )
        else:
            matches = np.array([
                mol is not None and mol.HasSubstructMatch(pattern)
                for mol in _TRAINING_MOLS
            ])
            candidate_idx = np.where(matches)[0]
            substructure_match_count = int(candidate_idx.size)

    if candidate_idx.size == 0:
        return {
            "threshold": threshold,
            "max_similarity": 0.0,
            "similarity_method": "top3_avg",
            "within_domain": False,
            "confidence_label": LOW_CONFIDENCE_LABEL,
            "nearest_training_compounds": [],
            "n_training_compounds": int(_INDEX["fingerprints"].shape[0]),
            "identified_name": None,
            "required_substructure_smarts": required_substructure_smarts,
            "substructure_error": substructure_error,
            "substructure_match_count": substructure_match_count,
        }

    sims_all = _tanimoto(query_fingerprint, _INDEX["fingerprints"][candidate_idx])
    order_local = np.argsort(sims_all)[::-1][: min(top_k, candidate_idx.size)]
    order = candidate_idx[order_local]
    sims = sims_all[order_local]  # sims[k]는 order[k]에 대응 (아래에서 order[0] 대신 0 인덱스로 참조)

    nearest = [
        {
            "compound_name": _name_with_cip(
                _display_name(str(_INDEX["compound_name"][i]), str(_INDEX["smiles"][i])),
                str(_INDEX["smiles"][i]),
            ),
            "smiles": str(_INDEX["smiles"][i]),
            "experimental_label": "BBB+" if _INDEX["label"][i] == 1 else "BBB-",
            "similarity": round(float(s), 4),
        }
        for i, s in zip(order, sims)
    ]

    top1_similarity = float(sims[0])
    if top1_similarity >= EXACT_MATCH_THRESHOLD:
        display_similarity = top1_similarity
        similarity_method = "top1"
    else:
        display_similarity = float(sims[:TOP_N_FOR_AVERAGE].mean())
        similarity_method = "top3_avg"

    within_domain = display_similarity >= threshold

    identified_name = None
    if query_smiles is not None:
        exact_matches = np.where(_INDEX["smiles"] == query_smiles)[0]
        for i in exact_matches:
            name = str(_INDEX["compound_name"][i]).strip()
            smi = str(_INDEX["smiles"][i])
            if smi.strip() in _KNOWN_NAME_CORRECTIONS:
                identified_name = _name_with_cip(_KNOWN_NAME_CORRECTIONS[smi.strip()], query_smiles)
                break
            if _is_real_name(name, smi):
                identified_name = _name_with_cip(_title_case(name), query_smiles)
                break

    return {
        "threshold": threshold,
        "max_similarity": round(display_similarity, 4),
        "similarity_method": similarity_method,
        "within_domain": within_domain,
        "confidence_label": "normal" if within_domain else LOW_CONFIDENCE_LABEL,
        "nearest_training_compounds": nearest,
        "n_training_compounds": int(_INDEX["fingerprints"].shape[0]),
        "identified_name": identified_name,
        "required_substructure_smarts": required_substructure_smarts,
        "substructure_error": substructure_error,
        "substructure_match_count": substructure_match_count,
    }
