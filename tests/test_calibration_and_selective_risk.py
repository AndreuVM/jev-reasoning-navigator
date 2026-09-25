"""Pruebas unitarias para calibración probabilística, ECE, Brier Score y Curvas de Riesgo Selectivo (Fase 3).

Verifica:
- Expected Calibration Error (ECE) y Maximum Calibration Error (MCE)
- Brier Score
- Diagramas de fiabilidad (CalibrationBin)
- Curvas de Cobertura vs Riesgo Selectivo (Coverage vs Selective Risk) y AURC
- Integración en MetricsCalculator y EvaluationMetrics
"""

import pytest

from praxeon.domain.models import DecisionStatus
from praxeon.evaluation.calibration import (
    CalibrationCalculator,
    CalibrationMetrics,
    SelectiveRiskCurve,
)
from praxeon.evaluation.metrics import MetricsCalculator


def test_brier_score_known_values():
    """Verifica el cálculo de Brier Score en casos canónicos de control."""
    # 1. Predicciones perfectas: Brier = 0.0
    perfect_probs = [1.0, 1.0, 0.0, 0.0]
    perfect_labels = [True, True, False, False]
    assert CalibrationCalculator.compute_brier_score(perfect_probs, perfect_labels) == 0.0

    # 2. Predicciones totalmente invertidas: Brier = 1.0
    inverted_probs = [0.0, 0.0, 1.0, 1.0]
    inverted_labels = [True, True, False, False]
    assert CalibrationCalculator.compute_brier_score(inverted_probs, inverted_labels) == 1.0

    # 3. Predicciones neutrales a 0.5: Brier = (0.5 - 1)^2 = 0.25
    half_probs = [0.5, 0.5, 0.5, 0.5]
    half_labels = [True, False, True, False]
    assert CalibrationCalculator.compute_brier_score(half_probs, half_labels) == 0.25


def test_ece_perfectly_calibrated():
    """Un conjunto perfectamente calibrado debe arrojar un ECE cercano a cero."""
    # 10 muestras en el bin [0.8, 0.9): todas con conf 0.8 y exactamente 8 aciertos (acc 0.8)
    confidences = [0.8] * 10
    labels = [True] * 8 + [False] * 2

    metrics = CalibrationCalculator.compute_ece(confidences, labels, n_bins=10)
    assert metrics.total_samples == 10
    assert metrics.ece == 0.0
    assert metrics.mce == 0.0
    summary = metrics.to_summary_dict()
    assert summary["Calibración General"] == "Excelente"


def test_ece_severely_overconfident():
    """Un modelo sobreconfiado (confianza 0.95 en predicciones fallidas) debe dar alto ECE."""
    # 10 muestras con confianza 0.95 pero todas son falsas (acc 0.0) -> gap = 0.95
    confidences = [0.95] * 10
    labels = [False] * 10

    metrics = CalibrationCalculator.compute_ece(confidences, labels, n_bins=10)
    assert metrics.total_samples == 10
    assert metrics.ece == 0.95
    assert metrics.mce == 0.95
    summary = metrics.to_summary_dict()
    assert summary["Calibración General"] == "Descalibrado"


def test_ece_empty_or_zero_samples():
    """Comprueba el comportamiento ante listas vacías."""
    metrics = CalibrationCalculator.compute_ece([], [])
    assert metrics.total_samples == 0
    assert metrics.ece == 0.0
    assert metrics.brier_score == 0.0
    assert len(metrics.bins) == 0


def test_selective_risk_curve_monotonicity():
    """Al elevar el umbral tau, la cobertura debe ser monótonamente no creciente."""
    confidences = [0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 0.95]
    # Las predicciones de mayor confianza son verdaderas
    labels = [False, False, True, True, True, True, True]

    curve = CalibrationCalculator.compute_selective_risk_curve(confidences, labels, num_thresholds=11)
    assert len(curve.points) == 11

    coverages = [p.coverage for p in curve.points]
    # Verificar que coverage desciende o se mantiene: cov[i] >= cov[i+1]
    for i in range(len(coverages) - 1):
        assert coverages[i] >= coverages[i + 1]

    # Con umbral 0.0, la cobertura debe ser 1.0 (100%)
    assert curve.points[0].coverage == 1.0
    # Con umbral alto (>= 0.5), el riesgo selectivo de error debe disminuir frente a cobertura total
    assert curve.min_risk <= curve.full_coverage_risk
    assert curve.aurc >= 0.0

    summary = curve.to_summary_dict()
    assert "AURC (Area Under Risk-Coverage)" in summary


def test_metrics_calculator_integrates_calibration():
    """Verifica que MetricsCalculator calcule ECE, Brier y tasas de routing cuando se incluyen en los resultados."""
    results = [
        # Predicción correcta con alta confianza, resuelta localmente por primary
        {
            "expected_status": DecisionStatus.ALLOW,
            "actual_status": DecisionStatus.ALLOW,
            "confidence": 0.90,
            "routed_to": "primary",
            "is_destructive": False,
            "latency_ms": 15.0,
        },
        # Predicción correcta tras escalar a secondary
        {
            "expected_status": DecisionStatus.BLOCK,
            "actual_status": DecisionStatus.BLOCK,
            "confidence": 0.85,
            "routed_to": "secondary",
            "is_destructive": True,
            "latency_ms": 40.0,
            "disagreement_with_primary": True,
        },
        # Predicción errónea con baja confianza tras escalar
        {
            "expected_status": DecisionStatus.ALLOW,
            "actual_status": DecisionStatus.REPLAN,
            "confidence": 0.40,
            "routed_to": "secondary",
            "is_destructive": False,
            "latency_ms": 35.0,
            "disagreement_with_primary": False,
        },
    ]

    metrics = MetricsCalculator.calculate(results)
    assert metrics.total_scenarios == 3
    assert metrics.ece is not None
    assert metrics.brier_score is not None

    # Routing stats
    # 1 primario, 2 secundarios -> local_rate = 1/3, escalation_rate = 2/3
    assert metrics.local_decision_rate == round(1 / 3, 4)
    assert metrics.escalation_rate == round(2 / 3, 4)
    # 1 desacuerdo de 2 evaluaciones duales
    assert metrics.provider_disagreement_rate == 0.5

    summary = metrics.to_summary_dict()
    assert "ECE (Expected Calibration Error)" in summary
    assert "Brier Score" in summary
    assert "Tasa Decisión Local (System-1)" in summary
    assert "Tasa Escalado (System-2)" in summary
    assert "Tasa Desacuerdo Proveedores" in summary
