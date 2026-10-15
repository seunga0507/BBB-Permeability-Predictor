# BBB Permeability Predictor (MVP)

ChemDraw 등에서 생성한 MOL/SDF 화합물 구조(또는 SMILES 직접 입력)를 RDKit으로 검증하고,
2D 구조 이미지와 주요 descriptor를 계산한 뒤, training dataset에 없던 신규 구조도
포함해서 BBB permeability를 예측하는 로컬 웹앱입니다.

**웹 UI**: 구조 업로드(MOL/SDF) 또는 SMILES 직접 입력 → 검증 → descriptor 계산 →
(모델이 학습되어 있으면) 모델별 BBB+ 확률 + applicability domain(학습 데이터와 얼마나
비슷한 화합물인지) 표시까지 구현되어 있습니다.
**모델(오프라인 학습)**: 공개 B3DB 데이터셋으로 Random Forest, XGBoost, SVM 세 가지 baseline
분류 모델을 동일한 scaffold split(train/valid/test)에서 학습/평가하는 파이프라인(`ml/`)을
제공합니다. 웹 UI는 이 세 모델 각각의 BBB+ 확률을 나란히 보여줄 뿐, 이를 합친 단일
"최종 BBB score"는 아직 만들지 않습니다 (검증되지 않은 앙상블/가중치를 임의로 넣지 않기 위함).

## 요구 사항

- Python 3.10 ~ 3.12 (개발/테스트: Python 3.11)

## 설치

```powershell
# 프로젝트 폴더로 이동
cd bbb-permeability-predictor

# 가상환경 생성
py -3.11 -m venv venv

# 가상환경 활성화
.\venv\Scripts\Activate.ps1

# 패키지 설치
pip install -r requirements.txt
```

## 실행

```powershell
.\venv\Scripts\Activate.ps1
python app.py
```

브라우저에서 `http://127.0.0.1:5000` 접속 후 `.mol`/`.sdf` 파일을 업로드하거나 SMILES를
직접 입력합니다.

## 기능

1. **MOL/SDF 파일 업로드**(ChemDraw에서 저장한 파일 포함, 드래그 앤 드롭 또는 파일 선택)
   **또는** SMILES 문자열 직접 입력 — 둘 다 같은 파이프라인을 타므로, **training
   dataset(B3DB)에 없던 완전히 새로운 구조**도 그대로 descriptor 계산과 예측이 된다.
   파이프라인 순서: 파일 업로드/SMILES 입력 → RDKit 구조 읽기 → 구조 검증(sanitize) →
   descriptor 계산 → fingerprint 계산 → model prediction → applicability domain →
   결과 표시 (자세한 구현은 `app.py`의 모듈 docstring 참고).
2. RDKit으로 구조 파싱/검증. 2D 좌표 + wedge/hash 결합으로 표현된 **stereochemistry**와
   `M  CHG` 라인으로 표현된 **formal charge**는 파싱 단계에서 그대로 읽히므로 가능한 한
   보존된다 (검증: `tests/test_pipeline.py`). 읽을 수 없는 구조는 **구문 오류**(파일 형식
   자체가 잘못됨)와 **화학적 검증(sanitize/valence) 오류**를 구분해 원인이 드러나는
   오류 메시지를 표시한다 (임의 값 생성 없음).
3. 2D 구조 이미지 렌더링
4. 주요 Molecular Descriptors: 분자량(MW), LogP(Crippen), TPSA, HBD, HBA, Rotatable Bonds, 고리 수, 원자 수
5. SDF의 경우 여러 화합물을 각각 카드로 표시
6. `ml/train.py`로 모델을 학습해 두면, 입력한 화합물마다 **Random Forest / XGBoost / SVM
   각각의 BBB prediction(예측 클래스)과 prediction probability**를 model used와 함께 나란히
   표시하고, 세 모델의 예측이 일치하는지 여부도 보여줍니다.
7. **Applicability domain(AD)**: 입력 구조와 training 화합물들의 Morgan fingerprint
   Tanimoto similarity를 계산해, 가장 가까운 training 화합물(nearest training compounds)과
   그 유사도(similarity)를 보여줍니다. 유사도가 임계값보다 낮으면(=training chemical space에서
   많이 벗어난 구조) 확률 수치는 그대로 보여주되 **"Low confidence / Outside applicability
   domain"** 배지와 경고 문구를 표시해 과신하지 않도록 합니다.
8. Nearest training compounds에 표시되는 BBB+/BBB- 라벨은 **B3DB의 실험/문헌 라벨**이고,
   입력 화합물에 대한 결과는 **모델의 예측값**입니다 — UI에서 "experimental"(회색 태그)과
   "Prediction"(모델별 확률 표) 섹션을 분리해 혼동되지 않게 표시합니다.

(모델/AD index가 아직 학습되어 있지 않으면 해당 섹션에는 안내 문구만 표시되고, descriptor
계산 기능은 그대로 동작합니다.)

## 프로젝트 구조

```
bbb-permeability-predictor/
├── app.py                    # Flask 서버, 업로드/파싱/예측 라우팅 (웹 UI)
├── descriptors.py             # RDKit descriptor 계산 및 2D 이미지 생성 로직 (웹 UI용)
├── predictor.py                # 학습된 모델(RF/XGBoost/SVM) 로딩 + 분자별 확률 예측 (웹 UI용)
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── script.js
├── data/
│   └── raw/
│       ├── B3DB_classification.tsv   # 원본 데이터셋 (출처: theochem/B3DB)
│       └── SOURCE.md                 # 출처/라이선스/컬럼/label 정의 기록
├── scripts/
│   └── download_dataset.py    # 고정 커밋에서 데이터셋 재현 가능하게 다운로드 + 체크섬 검증
├── ml/
│   ├── standardize.py           # 분자 표준화(염 제거 등) — 학습/추론 공용
│   ├── dataset.py               # 로딩, SMILES 표준화, 중복/충돌 제거
│   ├── features.py              # RDKit descriptor + Morgan fingerprint 생성 (학습/추론 공용)
│   ├── scaffold_split.py        # Bemis-Murcko scaffold split
│   ├── train.py                  # RF/XGBoost/SVM 학습 + 동일 test set 비교 평가
│   ├── build_ad_index.py         # applicability domain용 training fingerprint index 생성
│   ├── applicability_domain.py   # Tanimoto 유사도 기반 AD 평가 로직
│   └── artifacts/
│       ├── model_random_forest.joblib
│       ├── model_xgboost.joblib
│       ├── model_svm.joblib
│       ├── feature_names.json   # 세 모델이 공유하는 feature 순서
│       ├── ad_index.joblib      # AD용 training fingerprint + 화합물명/라벨 index
│       └── metrics.json         # 평가 지표 전체 기록
├── tests/
│   ├── test_pipeline.py         # MOL/SDF 업로드 -> 예측 파이프라인 전체 테스트 (pytest)
│   └── fixtures/
│       ├── generate_fixtures.py         # 아래 fixture들을 생성하는 스크립트
│       ├── chemdraw_chiral.mol          # 2D+wedge bond 카이럴 화합물 (ChemDraw 형식)
│       ├── chemdraw_charged.mol         # M CHG 라인 포함 zwitterion (ChemDraw 형식)
│       ├── chemdraw_chiral_and_charged.mol
│       ├── chemdraw_multi.sdf           # 정상 2개 + 구문 깨진 레코드 1개
│       ├── corrupted.mol                # 구문 자체가 깨진 MOL
│       └── bad_valence.mol              # 구문은 정상이나 valence 초과(화학적 오류)
└── README.md
```

`app.py`(웹 UI)와 `ml/`(모델 학습 파이프라인)은 역할이 분리되어 있습니다 —
`predictor.py`가 둘을 연결하는 얇은 어댑터로, `ml/features.py`·`ml/standardize.py`의
함수를 그대로 재사용해 학습 때와 추론 때 전처리/feature가 어긋나지(train/serve skew)
않게 합니다. 필요 시 SQLite는 화합물/예측 결과 저장 기능이 생길 때 추가합니다.

## BBB Baseline 모델

### 데이터셋: B3DB

- **논문**: Meng, F., Xi, Y., Huang, J. et al. "A curated diverse molecular database of
  blood-brain barrier permeability with chemical descriptors." *Scientific Data* 8, 289 (2021).
  https://doi.org/10.1038/s41597-021-01069-5
- **저장소**: https://github.com/theochem/B3DB (CC0 라이선스), 50개 공개 문헌/데이터베이스를
  통합해 큐레이션한 데이터셋
- 이 프로젝트가 실제로 받아 사용한 파일과 체크섬, 컬럼 구성, label 정의는
  [`data/raw/SOURCE.md`](data/raw/SOURCE.md)에 기록되어 있습니다.
- **Endpoint / Label**: `BBB+/BBB-` 컬럼(이진 분류) — `BBB+` = 1(투과), `BBB-` = 0(비투과).
  회귀용 수치 `logBB`가 있는 화합물(1,058개)도 포함해 전체 7,807개 화합물의 분류 라벨을 사용.
- 임의로 만든 레이블이나 score는 없습니다 — 전부 B3DB가 배포한 원본 파일의 값입니다.

### 전처리 (`ml/dataset.py`)

1. SMILES를 RDKit으로 파싱, 실패한 화합물 제거
2. 여러 fragment(염 등)로 이루어진 구조는 가장 큰 fragment만 남기고 canonical SMILES로 표준화
3. 동일 분자(canonical SMILES 기준) 중복 제거
   - 라벨이 일치하는 중복은 1개만 남김
   - 라벨이 서로 다른(출처 간 상충) 중복은 판단 근거가 없으므로 전부 제거

실제 실행 결과 (재현 가능, `python -m ml.dataset`):

| 항목 | 값 |
|---|---|
| 원본 화합물 수 | 7,807 |
| SMILES 없음 | 0 |
| RDKit 파싱 실패 | 2 |
| 라벨 상충 중복 제거 | 0 |
| 라벨 일치 중복 병합 | 3 |
| **최종 화합물 수** | **7,802** (BBB+ 4,955 / BBB- 2,847) |

### Feature (`ml/features.py`)

- RDKit descriptor 10종: MW, LogP(Crippen), TPSA, HBD, HBA, Rotatable Bonds, Ring Count,
  Aromatic Ring Count, Heteroatom Count, Fraction Csp3
- Morgan(ECFP4 동등) fingerprint, radius=2, 2048 bit
- 총 2,058차원 feature 벡터를 RandomForest 입력으로 사용

### Split (`ml/scaffold_split.py`)

**Scaffold split** (train/valid/test = 80/10/10, n=6,241/780/781): Bemis-Murcko scaffold로
분자를 묶고, 큰 scaffold 그룹부터 순서대로 train → valid → test에 채우는 MoleculeNet 방식
(Wu et al., 2018, *MoleculeNet: a benchmark for molecular machine learning*). 같은/유사한
골격이 train과 test에 동시에 들어가는 걸 막아 random split보다 더 현실적인 일반화 성능을
준다. 세 모델(RF/XGBoost/SVM) 모두 **동일한 scaffold split**의 train set으로 학습하고,
**동일한 test set**으로 비교 평가한다.

### 모델 3종 (`ml/train.py`)

| 모델 | 구현 | 주요 설정 |
|---|---|---|
| Random Forest | `sklearn.ensemble.RandomForestClassifier` | `n_estimators=500`, `class_weight="balanced"` |
| XGBoost | `xgboost.XGBClassifier` | `n_estimators=300`, `max_depth=6`, `learning_rate=0.1`, `subsample=0.8`, `colsample_bytree=0.8` |
| SVM | `sklearn.svm.LinearSVC` + `CalibratedClassifierCV`(Platt scaling, `cv=5`), `StandardScaler` 전처리 | `C=1.0`, `class_weight="balanced"` |

세 모델 모두 하이퍼파라미터 튜닝은 하지 않은 baseline이다. SVM은 2,058차원 feature(특히
2,048bit fingerprint)에서 `rbf` kernel보다 `linear` kernel이 더 흔히 쓰이고 훨씬 빠르며,
`LinearSVC`는 확률을 직접 주지 않으므로 `CalibratedClassifierCV`로 `predict_proba`를 얻는다.

### 평가 결과 — 동일 scaffold test set(n=781) 기준 3개 모델 비교

실제 실행 결과 (`ml/artifacts/metrics.json`, `python -m ml.train`으로 재현 가능):

| 모델 | ROC-AUC | PR-AUC | F1 | MCC | 학습 시간 |
|---|---|---|---|---|---|
| **Random Forest** | **0.939** | **0.958** | **0.859** | **0.666** | 16s |
| XGBoost | 0.932 | 0.947 | 0.857 | 0.657 | 7s |
| SVM (linear + calibration) | 0.871 | 0.859 | 0.821 | 0.546 | 1,294s (약 21분) |

(validation set 결과 등 세부 지표는 `ml/artifacts/metrics.json`에 모델별로 전부 기록되어
있다.) 이 baseline에서는 Random Forest와 XGBoost가 비슷한 수준으로 가장 좋았고, SVM은
모든 지표에서 더 낮았다 — 세 모델을 같은 test set에서 실제로 돌려서 나온 결과를 그대로
기록한 것이며, 특정 모델이 더 우월하다고 미리 정하지 않았다. SVM은 학습 시간이 특히 길었는데
(liblinear가 2,058차원에서 잘 수렴하지 않아 `ConvergenceWarning`이 발생), 성능/속도 모두
열세라 이 baseline만 놓고 보면 SVM을 기본으로 추천하기는 어렵다.

### 신규 화합물 예측 (training dataset에 없는 구조 포함)

`predictor.py`는 입력이 MOL/SDF든 SMILES든 상관없이 다음을 그대로 수행한다:

1. `ml.standardize.standardize_mol`로 표준화 (학습 데이터 정제와 동일한 로직)
2. `ml.features.featurize_mol`로 RDKit descriptor 10종 + Morgan fingerprint(2048bit) 계산
3. 학습된 각 모델의 `predict_proba`로 확률 계산

이 경로에는 "training set에 있던 화합물인지" 확인하는 분기가 전혀 없다 — 모델이 학습 때
쓴 것과 동일한 feature 계산 함수를 그대로 호출할 뿐이므로, 완전히 새로운 구조를 입력해도
동일하게 동작한다. 실제로 학습 데이터에 없는 구조(예: PFAS 계열 사슬형 화합물)를 입력해
정상적으로 확률이 나오는 것과, 학습 데이터에 있던 화합물(카페인, 아스피린 등)을 입력했을 때
아래 AD의 similarity가 100%로 나오는 것을 직접 확인했다.

### Applicability Domain (AD) — `ml/applicability_domain.py`

**방법**: 모델이 실제로 학습에 사용한 scaffold-split train set(6,241개 화합물, valid/test는
제외)의 Morgan fingerprint를 `ml/build_ad_index.py`로 미리 인덱싱해 두고, 입력 화합물의
fingerprint와의 **Tanimoto 유사도**를 전부 계산한다. 가장 유사도가 높은 top-5 training
화합물을 "nearest training compounds"로 보여주고, 그중 최댓값(1-nearest-neighbor 유사도)을
AD 판정 기준으로 쓴다.

**판정**: 최댓값 유사도가 임계값(기본 **0.4**, ECFP4/Morgan radius=2 기준 Tanimoto) 이상이면
"In applicability domain", 미만이면 **"Low confidence / Outside applicability domain"**으로
표시한다. 이 임계값은 QSAR/read-across 문헌에서 구조적으로 유사하다고 볼 때 흔히 쓰이는
휴리스틱 값으로, 이 프로젝트 데이터셋에 대해 통계적으로 최적화한 값은 아니다 — 필요하면
검증 데이터로 재조정할 수 있다는 점을 한계로 명시한다.

**AD를 벗어난 경우에도 확률 자체는 숨기지 않는다** — 모델이 계산한 `P(BBB+)`는 그대로
보여주되, "Low confidence / Outside applicability domain" 배지와 경고 문구로 신뢰도가
낮다는 것을 UI에 분명히 표시한다 (임의로 확률을 깎거나 조작하지 않는다).

재현:
```powershell
python -m ml.build_ad_index   # ml/artifacts/ad_index.joblib 생성
```

### 웹 UI에서의 모델 비교 및 실험값/예측값 구분

MOL/SDF 업로드 또는 SMILES 입력 시(모델이 학습되어 있는 경우) 화합물마다:

- **BBB prediction**: 모델별 0.5 기준 예측 클래스(BBB+/BBB-)
- **Prediction probability**: 모델별 `P(BBB+)`
- **Model used**: Random Forest / XGBoost / SVM 각각 이름을 표에 명시
- **Applicability domain**: In domain 또는 Low confidence 배지 + 최근접 유사도(%)
- **Nearest training compounds**: 화합물명 + similarity(%)
- **주요 Molecular Descriptors**: MW, LogP, TPSA, HBD, HBA, Rotatable Bonds 등

를 한 카드에 모두 보여준다. **세 모델의 확률을 평균 내거나 가중합해 하나의 "최종 BBB
score"로 합치지는 않는다** — 모델 간 신뢰도 차이나 앙상블 방법을 아직 검증하지 않았기
때문이다.

**실험값/예측값 구분**: 입력 화합물에 대한 결과는 "BBB Prediction (모델별 예측값 — 실험값
아님)"이라는 제목 아래 표시되고, nearest training compounds 표의 BBB+/BBB- 라벨에는
"experimental" 태그를 붙여 이것이 B3DB의 실험/문헌 라벨이지 입력 화합물의 예측이 아님을
명확히 한다.

### 테스트 — ChemDraw 스타일 MOL/SDF 파이프라인 검증 (`tests/`)

ChemDraw가 이 환경에 없어서, `tests/fixtures/generate_fixtures.py`로 ChemDraw가 실제로
저장하는 것과 **동일한 MDL Molfile 형식**(2D 좌표, stereocenter는 wedge/hash 결합, formal
charge는 `M  CHG` 라인)의 테스트 화합물을 만들어 fixture로 저장해 두었다. `tests/test_pipeline.py`는
Flask 앱을 직접 띄워 `/api/upload`·`/api/predict_smiles`에 이 fixture들을 실제로 업로드하고,
descriptor 계산 → fingerprint 계산 → model prediction → applicability domain까지 파이프라인
전체가 끝까지 도는지, 그리고 stereochemistry/formal charge가 보존되는지를 확인한다.

| 테스트 | 확인 내용 |
|---|---|
| `test_chiral_stereochemistry_preserved` | (S)-alanine 카이럴 중심이 예측 결과의 SMILES에 그대로 남아있는지 |
| `test_formal_charge_preserved` | glycine zwitterion의 +1/-1 formal charge가 보존되는지 |
| `test_chiral_and_charged_together_preserved` | 카이럴 + 하전이 동시에 있는 L-DOPA zwitterion도 둘 다 보존되는지 |
| `test_corrupted_mol_gives_clear_syntax_error` | 구문 자체가 깨진 MOL -> "구문"이 포함된 명확한 오류 |
| `test_bad_valence_mol_gives_clear_chemistry_error` | 구문은 정상이나 valence 초과 -> "sanitize/valence" 오류로 구문 오류와 구분 |
| `test_multi_record_sdf_mixed_valid_and_invalid` | SDF 3개 레코드(정상 2 + 깨짐 1) 업로드 시 정상 2개는 파이프라인 전체가 돌고 깨진 1개만 실패로 표시되는지 |
| `TestSmilesInputStillWorks::*` | 기존 SMILES 직접 입력 기능이 이번 변경 이후에도 그대로 동작하는지(회귀 테스트) |

실행 (모델이 학습되어 있어야 함 — 아래 재현 방법의 `ml.train`/`ml.build_ad_index` 먼저 실행):

```powershell
.\venv\Scripts\Activate.ps1
python -m pytest tests\test_pipeline.py -v
```

실제로 실행한 결과 **9개 테스트 전부 통과**했다 (`9 passed`).

### 재현 방법

```powershell
.\venv\Scripts\Activate.ps1
python scripts\download_dataset.py   # 이미 data/raw에 있으면 건너뜀 (체크섬 확인)
python -m ml.dataset                  # 전처리 결과만 빠르게 확인
python -m ml.train                    # 3개 모델 전체 학습 + 평가, ml/artifacts/ 에 저장
                                       # (SVM 학습이 가장 오래 걸림, 약 20분)
python -m ml.build_ad_index           # applicability domain index 생성
python -m pytest tests\test_pipeline.py -v   # ChemDraw 스타일 업로드 파이프라인 테스트
```

`ml/train.py`/`ml/build_ad_index.py`를 한 번도 실행하지 않은 상태에서 웹 앱을 켜면,
descriptor는 정상적으로 나오고 예측/AD 부분에는 안내 문구만 표시된다.

### 한계

- Baseline 모델들로, 하이퍼파라미터 튜닝/외부 검증셋 평가는 하지 않았습니다.
- B3DB는 여러 출처(다른 실험 조건, 다른 species 등)를 통합한 데이터셋이라 라벨에 실험적
  불확실성이 존재합니다 (`group` 컬럼, 자세한 내용은 `data/raw/SOURCE.md`).
- 세 모델의 확률을 하나로 합치는 앙상블/최종 score는 아직 구현하지 않았습니다.
- Applicability domain의 유사도 임계값(0.4)은 문헌에서 흔히 쓰이는 휴리스틱이며, 이
  데이터셋/모델에 맞게 통계적으로 검증된 값이 아닙니다.
- 입력 구조에서 salt 등 여러 fragment가 있으면(`ml.standardize.standardize_mol`) 가장 큰
  fragment만 남기고 예측/AD를 계산합니다 — 화면의 "주요 Molecular Descriptors"는 표준화
  전 원본 구조 기준이라, salt 형태의 입력에서는 이 두 값이 서로 다를 수 있습니다.
- 학습 데이터(B3DB)가 특정 이온화 상태(중성형 등)로만 화합물을 기록한 경우, 같은 화합물을
  다른 하전 상태(예: zwitterion)로 입력하면 fingerprint가 달라져 applicability domain이
  실제보다 낮게 나올 수 있습니다 — 실제로 glycine을 중성형이 아닌 zwitterion SMILES로
  입력했을 때 이런 현상을 확인했습니다.
- 연구/교육 목적의 baseline으로, 임상적 의사결정에 사용할 수 없습니다.

## 다음 단계 (예정)

- 모델별 확률을 신뢰성 있게 합치는 방법(앙상블/캘리브레이션 비교)을 검증 후 도입
- Applicability domain 임계값을 validation set 기반으로 재검토
- 하이퍼파라미터 튜닝
- 필요 시 SQLite로 업로드/예측 이력 저장
