import os
from unittest.mock import Mock, patch

from backend.ai.engine import AIEngine, ROOT_DIR


def test_resolve_custom_model_path_prefers_classifier():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()
    assert engine.custom_model_path == os.path.join(ROOT_DIR, "classifier")


def test_analyze_message_uses_binary_classifier_as_additive_signal():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "1", "score": 0.91}])
    engine.toxicity_model = None

    analysis = engine.analyze_message("send money now")

    assert analysis["risk_score"] >= 91.0
    assert analysis["action"] == "block"
    assert analysis["details"]["binary_label"] == "1"
    assert analysis["details"]["custom_model_path"] == os.path.join(ROOT_DIR, "classifier")
