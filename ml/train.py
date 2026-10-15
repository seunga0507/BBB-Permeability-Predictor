"""B3DB 기반 BBB permeability baseline 모델 학습/평가 스크립트.

실행: (프로젝트 루트에서)
    venv\\Scripts\\python.exe -m ml.train

수행 절차:
    1. data/raw/B3DB_classification.tsv 로딩, SMILES 표준화, 중복/충돌 제거
    2. RDKit descriptor + Morgan fingerprint feature 생성
    3. scaffold split (80/10/10) 으로 train/valid/test 분리
    4. 동일한 scaffold split(train/valid/test)에서 세 가지 baseline 모델을 각각 학습
       - Random Forest, XGBoost, SVM(linear kernel + Platt calibration)
    5. 세 모델을 **같은 test set**에서 ROC-AUC / PR-AUC / F1 / MCC로 비교 평가
    6. 학습된 모델(ml/artifacts/model_<name>.joblib)과 비교 결과(metrics.json) 저장

주의: 세 모델의 확률을 각각 저장/비교할 뿐, 이들을 합쳐 하나의 "최종 BBB score"를
만들지는 않는다 (앙상블/가중평균 없음).
"""

import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    matthews_corrcoef,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from xgboost import XGBClassifier

from ml.dataset import load_and_clean
from ml.features import DESCRIPTOR_NAMES, FP_N_BITS, feature_names, featurize
from ml.scaffold_split import scaffold_split

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

RANDOM_STATE = 42

MODEL_PARAMS = {
    "random_forest": dict(
        n_estimators=500,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    ),
    "xgboost": dict(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    ),
    "svm": dict(
        # feature 차원(2058)이 크고 fingerprint가 이진 벡터라 linear kernel이
        # rbf보다 빠르고 흔히 더 잘 맞는다. LinearSVC는 확률을 직접 주지 않으므로
        # CalibratedClassifierCV(Platt scaling)로 predict_proba를 얻는다.
        base_estimator="LinearSVC",
        C=1.0,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        calibration_cv=5,
    ),
}


def build_model(name: str):
    params = MODEL_PARAMS[name]
    if name == "random_forest":
        return RandomForestClassifier(**params)
    if name == "xgboost":
        return XGBClassifier(**params)
    if name == "svm":
        base = LinearSVC(
            C=params["C"],
            class_weight=params["class_weight"],
            random_state=params["random_state"],
            max_iter=5000,
        )
        calibrated = CalibratedClassifierCV(base, cv=params["calibration_cv"])
        return Pipeline([("scaler", StandardScaler()), ("svm", calibrated)])
    raise ValueError(f"unknown model: {name}")


def evaluate(model, X, y) -> dict:
    proba = model.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)
    return {
        "n": int(len(y)),
        "roc_auc": float(roc_auc_score(y, proba)),
        "pr_auc": float(average_precision_score(y, proba)),
        "f1": float(f1_score(y, pred)),
        "mcc": float(matthews_corrcoef(y, pred)),
    }


def train_and_evaluate(name, X, y, train_idx, valid_idx, test_idx):
    print(f"[{name}] training on scaffold split train set (n={len(train_idx)})...")
    model = build_model(name)
    t0 = time.time()
    model.fit(X[train_idx], y[train_idx])
    train_seconds = round(time.time() - t0, 2)
    print(f"[{name}] done in {train_seconds}s")

    result = {
        "train_seconds": train_seconds,
        "valid": evaluate(model, X[valid_idx], y[valid_idx]),
        "test": evaluate(model, X[test_idx], y[test_idx]),
    }
    return model, result


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    cleaned, report = load_and_clean()
    print("Cleaning report:", report)

    X, names = featurize(cleaned["canonical_smiles"])
    y = cleaned["label"].to_numpy()
    print(f"Feature matrix: {X.shape} ({len(DESCRIPTOR_NAMES)} descriptors + {FP_N_BITS} fp bits)")

    train_idx, valid_idx, test_idx = scaffold_split(cleaned["canonical_smiles"])
    print(f"Scaffold split sizes: train={len(train_idx)} valid={len(valid_idx)} test={len(test_idx)}")

    split_sizes = {
        "n_train": int(len(train_idx)),
        "n_valid": int(len(valid_idx)),
        "n_test": int(len(test_idx)),
    }

    per_model_results = {}
    for model_name in ("random_forest", "xgboost", "svm"):
        model, result = train_and_evaluate(model_name, X, y, train_idx, valid_idx, test_idx)
        per_model_results[model_name] = result

        model_path = ARTIFACTS_DIR / f"model_{model_name}.joblib"
        joblib.dump(model, model_path)
        print(f"[{model_name}] saved model to {model_path}")

    (ARTIFACTS_DIR / "feature_names.json").write_text(
        json.dumps(feature_names(), indent=2), encoding="utf-8"
    )

    metrics = {
        "dataset": {
            "n_raw": report.n_raw,
            "n_missing_smiles": report.n_missing_smiles,
            "n_unparseable_smiles": report.n_unparseable,
            "n_duplicate_conflicting_dropped": report.n_duplicate_conflicting,
            "n_duplicate_consistent_merged": report.n_duplicate_consistent_merged,
            "n_final": report.n_final,
            "n_positive_BBB+": int((y == 1).sum()),
            "n_negative_BBB-": int((y == 0).sum()),
        },
        "features": {
            "n_descriptors": len(DESCRIPTOR_NAMES),
            "descriptor_names": DESCRIPTOR_NAMES,
            "fingerprint": f"Morgan/ECFP4-equivalent, radius=2, {FP_N_BITS} bits",
            "n_features_total": X.shape[1],
        },
        "split": {"method": "bemis_murcko_scaffold", **split_sizes},
        "models": {
            name: {"params": MODEL_PARAMS[name], **per_model_results[name]}
            for name in per_model_results
        },
    }

    metrics_path = ARTIFACTS_DIR / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Saved metrics to {metrics_path}")

    print("\n=== 동일 scaffold test set 기준 모델 비교 (test) ===")
    header = f"{'model':<15}{'ROC-AUC':>10}{'PR-AUC':>10}{'F1':>10}{'MCC':>10}"
    print(header)
    for name, result in per_model_results.items():
        t = result["test"]
        print(f"{name:<15}{t['roc_auc']:>10.3f}{t['pr_auc']:>10.3f}{t['f1']:>10.3f}{t['mcc']:>10.3f}")


if __name__ == "__main__":
    main()
