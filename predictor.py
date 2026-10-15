"""웹 UI에서 쓰는 BBB permeability 예측 모듈.

ml/train.py 에서 학습해 ml/artifacts/ 에 저장한 Random Forest, XGBoost, SVM 모델을
불러와, 업로드/입력된 분자(학습 데이터에 없던 신규 구조 포함)마다:
  - 모델별 BBB+ 확률 예측
  - fingerprint 유사도 기반 applicability domain(AD) 평가
를 계산한다.

주의:
  - 세 모델의 확률을 그대로 각각 보여줄 뿐, 이들을 합쳐 하나의 "최종 BBB score"를
    만들지 않는다 (아직 검증되지 않은 앙상블/가중치를 임의로 도입하지 않기 위함).
  - applicability domain에서 벗어난(training chemical space와 많이 다른) 구조는
    "Low confidence / Outside applicability domain"으로 표시하고, 예측 확률 자체는
    그대로 보여주되 신뢰도가 낮다는 점을 명시한다.

필수 Moiety(SMARTS) 필터가 걸린 경우의 예측 모드 3가지("prediction_mode"):
  - "global": 필터가 없거나(기본), 필터는 있지만 Nearest training compound 검색에만
    쓰이고 예측 자체는 평소처럼 전체 6,241개로 학습된 고정 모델을 그대로 쓴다.
  - "subset_retrain": 매칭된 training 화합물이 충분히 많고(READ_ACROSS_MIN_TOTAL개
    이상) 양쪽 라벨(BBB+/BBB-)도 충분히 섞여 있으면(각 READ_ACROSS_MIN_PER_CLASS개
    이상), RF/XGBoost/SVM을 그 매칭된 화합물만으로 그 자리에서 재학습해서 예측한다.
  - "read_across": 매칭된 화합물이 너무 적거나 한쪽 라벨로 치우쳐 있으면(분류기
    학습 자체가 불안정하거나 SVM처럼 클래스가 1개뿐이면 학습이 아예 불가능해서)
    재학습 대신, 가장 가까운 매칭 화합물들의 실험 라벨을 구조 유사도로 가중 평균해서
    보여준다(모델 예측이 아니라 "비슷한 기존 화합물의 실제 실험값을 참고"하는 방식).
  - 매칭된 화합물이 0개면 predictions는 빈 dict로 둔다(비교할 근거가 전혀 없으므로
    프런트엔드가 예측 자체를 생략하고 그 이유를 표시한다).
"""

from pathlib import Path

import joblib
import numpy as np
from rdkit import Chem
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from xgboost import XGBClassifier

from ml import applicability_domain
from ml.applicability_domain import READ_ACROSS_MIN_PER_CLASS, READ_ACROSS_MIN_TOTAL
from ml.features import DESCRIPTOR_NAMES, featurize, featurize_mol
from ml.standardize import standardize_mol

ARTIFACTS_DIR = Path(__file__).resolve().parent / "ml" / "artifacts"

MODEL_FILES = {
    "random_forest": "model_random_forest.joblib",
    "xgboost": "model_xgboost.joblib",
    "svm": "model_svm.joblib",
}

MODEL_LABELS = {
    "random_forest": "Random Forest",
    "xgboost": "XGBoost",
    "svm": "SVM",
}

_FP_START = len(DESCRIPTOR_NAMES)

# 매칭된 화합물만으로 즉석 재학습할 때 쓰는 하이퍼파라미터. RF/XGBoost는
# ml/train.py와 동일하게 맞췄고(값이 커도 수십~수백 개 데이터로 학습하는 데는
# 1초 안팎이라 속도 문제 없음), SVM의 Platt calibration만 cv=3으로 낮췄다 —
# READ_ACROSS_MIN_PER_CLASS(5)에 딱 맞춘 cv=5는 class당 정확히 5개일 때 폴드마다
# 여유가 전혀 없어 불안정할 수 있어서, 더 작은 데이터에서도 안전한 값으로 뒀다.
_SUBSET_RANDOM_STATE = 42
_SUBSET_SVM_CALIBRATION_CV = 3


def _load_models() -> dict:
    models = {}
    for name, filename in MODEL_FILES.items():
        path = ARTIFACTS_DIR / filename
        if path.exists():
            models[name] = joblib.load(path)
    return models


_MODELS = _load_models()


def models_available() -> bool:
    return len(_MODELS) > 0


def ad_available() -> bool:
    return applicability_domain.ad_index_available()


def _build_subset_model(name: str):
    if name == "random_forest":
        return RandomForestClassifier(
            n_estimators=500,
            class_weight="balanced",
            random_state=_SUBSET_RANDOM_STATE,
            n_jobs=-1,
        )
    if name == "xgboost":
        return XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=_SUBSET_RANDOM_STATE,
            n_jobs=-1,
        )
    if name == "svm":
        base = LinearSVC(
            C=1.0,
            class_weight="balanced",
            random_state=_SUBSET_RANDOM_STATE,
            max_iter=5000,
        )
        calibrated = CalibratedClassifierCV(base, cv=_SUBSET_SVM_CALIBRATION_CV)
        return Pipeline([("scaler", StandardScaler()), ("svm", calibrated)])
    raise ValueError(f"unknown model: {name}")


def _predict_with_global_models(full_vector: np.ndarray) -> dict:
    """전체 6,241개로 미리 학습해둔 고정 모델(RF/XGBoost/SVM)로 예측한다."""
    if not _MODELS:
        return {}
    x = full_vector.reshape(1, -1)
    predictions = {}
    for name, model in _MODELS.items():
        proba = float(model.predict_proba(x)[0, 1])
        predictions[name] = {
            "label": MODEL_LABELS[name],
            "probability": round(proba, 4),
            "predicted_class": "BBB+" if proba >= 0.5 else "BBB-",
        }
    return predictions


def _predict_with_subset_models(full_vector: np.ndarray, subset_smiles: np.ndarray, subset_labels: np.ndarray) -> dict:
    """매칭된 training 화합물만으로 RF/XGBoost/SVM을 그 자리에서 재학습해 예측한다."""
    X_subset, _ = featurize(subset_smiles)
    y_subset = subset_labels.astype(int)
    x_query = full_vector.reshape(1, -1)

    predictions = {}
    for name in MODEL_FILES:
        model = _build_subset_model(name)
        model.fit(X_subset, y_subset)
        proba = float(model.predict_proba(x_query)[0, 1])
        predictions[name] = {
            "label": MODEL_LABELS[name],
            "probability": round(proba, 4),
            "predicted_class": "BBB+" if proba >= 0.5 else "BBB-",
        }
    return predictions


def _read_across_reason(n_matched: int, n_positive: int, n_negative: int) -> tuple[str, str]:
    """(요약 한 줄, 미충족 원인 한 줄) — 프런트엔드가 한 박스 안에 두 줄로 보여준다."""
    summary = "필수 Moiety를 포함하는 Training 화합물이 학습 가능 기준에 충족하지 못하여 Read-across 방식 사용"
    if n_matched < READ_ACROSS_MIN_TOTAL:
        detail = f"미충족 원인 : 학습 화합물 개수 미달 (학습 가능 기준 : {READ_ACROSS_MIN_TOTAL}개 이상)"
    else:
        detail = (
            f"미충족 원인 : BBB+/− 불균형 — BBB+ {n_positive}개 / BBB− {n_negative}개 "
            f"(학습 가능 기준 : 양쪽 각 {READ_ACROSS_MIN_PER_CLASS}개 이상)"
        )
    return summary, detail


def predict(mol: Chem.Mol, required_substructure_smarts: str | None = None) -> dict:
    """분자 하나 -> {"predictions": {...}, "applicability_domain": {...} | None, "prediction_mode": str, ...}.

    학습된 모델 파일이 없으면 predictions는 빈 dict. mol은 학습 때와 동일하게
    표준화(염 제거 등)한 뒤 feature를 계산하므로, training set에 없던 완전히 새로운
    구조라도 그대로 예측할 수 있다.

    required_substructure_smarts가 주어지면, applicability domain의 "가장 가까운
    training 화합물" 검색을 그 부분구조를 실제로 포함하는 training 화합물로만
    제한하고(SMARTS 부분구조 매칭, Tanimoto 유사도와는 별개의 하드 필터), 예측
    자체도 매칭된 화합물 수/라벨 분포에 따라 "global"/"subset_retrain"/"read_across"
    세 모드 중 하나로 수행한다(모듈 docstring 참고).
    """
    result = {
        "predictions": {},
        "applicability_domain": None,
        "prediction_mode": "global",
        "read_across_reason": None,
        "read_across_detail": None,
        "global_predictions": None,
    }

    std_mol = standardize_mol(mol)
    if std_mol is None:
        return result

    query_smiles = Chem.MolToSmiles(std_mol)
    full_vector = featurize_mol(std_mol)
    fingerprint = full_vector[_FP_START:]

    candidate_idx = None
    if required_substructure_smarts:
        candidate_idx = applicability_domain.match_substructure_candidates(required_substructure_smarts)

    if candidate_idx is None:
        # 필터가 없거나 SMARTS 파싱 실패 — 평소처럼 전체 6,241개로 학습된 고정 모델 사용.
        result["predictions"] = _predict_with_global_models(full_vector)
        result["prediction_mode"] = "global"
    elif candidate_idx.size == 0:
        # 매칭된 training 화합물이 0개 — 비교할 근거가 없으므로 예측 자체를 생략.
        result["prediction_mode"] = "none"
    else:
        n_positive, n_negative = applicability_domain.candidate_class_balance(candidate_idx)
        sufficient_for_retrain = (
            candidate_idx.size >= READ_ACROSS_MIN_TOTAL
            and n_positive >= READ_ACROSS_MIN_PER_CLASS
            and n_negative >= READ_ACROSS_MIN_PER_CLASS
        )
        if sufficient_for_retrain:
            subset_smiles, subset_labels = applicability_domain.candidate_training_subset(candidate_idx)
            result["predictions"] = _predict_with_subset_models(full_vector, subset_smiles, subset_labels)
            # 필터 없는 전체 6,241개 기준 예측도 같이 계산해서, 화면에서 "전체 기준
            # 예측 보러가기" 팝업으로 바로 비교해볼 수 있게 한다(모델은 이미 메모리에
            # 로드돼 있어 재학습 없이 바로 추론만 하므로 비용이 거의 없다).
            result["global_predictions"] = _predict_with_global_models(full_vector)
            result["prediction_mode"] = "subset_retrain"
            result["retrain_info"] = {
                "n_compounds": int(candidate_idx.size),
                "n_positive": n_positive,
                "n_negative": n_negative,
            }
        else:
            result["prediction_mode"] = "read_across"
            result["read_across_reason"], result["read_across_detail"] = _read_across_reason(
                int(candidate_idx.size), n_positive, n_negative
            )
            # read-across일 때도 "전체 6,241개 기준 예측 보러가기" 팝업을 띄울 수
            # 있도록 전역 모델 예측을 같이 계산해둔다(subset_retrain과 동일한 이유).
            result["global_predictions"] = _predict_with_global_models(full_vector)

    result["applicability_domain"] = applicability_domain.assess(
        fingerprint,
        query_smiles=query_smiles,
        required_substructure_smarts=required_substructure_smarts,
    )

    return result
