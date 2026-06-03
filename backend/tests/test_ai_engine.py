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


def test_analyze_message_downweights_binary_only_false_positive_for_short_roman_urdu():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "1", "score": 0.99}])
    engine.toxicity_model = None

    analysis = engine.analyze_message("kahan ho")

    assert analysis["risk_score"] < engine.flag_threshold
    assert analysis["label"] == "Safe"
    assert analysis["action"] == "allow"


def test_analyze_message_keeps_roman_urdu_threats_flagged():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "0", "score": 0.60}])
    engine.toxicity_model = None

    analysis = engine.analyze_message("tujhe dekh lunga")

    assert analysis["risk_score"] >= 90.0
    assert analysis["label"] == "Threat"
    assert analysis["action"] == "block"


def test_analyze_message_keeps_common_roman_urdu_small_talk_safe():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "1", "score": 0.97}])
    engine.toxicity_model = None

    for text in ["kesi ho", "kal class kab hai", "pdf share kar do", "kidhar ho yaar"]:
        analysis = engine.analyze_message(text)
        assert analysis["label"] == "Safe", text
        assert analysis["action"] == "allow", text


def test_analyze_message_flags_roman_urdu_abuse():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "0", "score": 0.55}])
    engine.toxicity_model = None

    analysis = engine.analyze_message("tum bohat ghatiya aur bewaqoof ho")

    assert analysis["risk_score"] >= engine.flag_threshold
    assert analysis["label"] == "Unsafe"
    assert analysis["action"] == "flag"


def test_analyze_message_flags_roman_urdu_scam_prompt():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "0", "score": 0.55}])
    engine.toxicity_model = None

    analysis = engine.analyze_message("apna otp aur easypaisa account number send karo")

    assert analysis["risk_score"] >= engine.flag_threshold
    assert analysis["label"] == "Scam"
    assert analysis["action"] == "flag"


def test_analyze_message_flags_blackmail_phrase():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "0", "score": 0.55}])
    engine.toxicity_model = None

    analysis = engine.analyze_message("paise do warna expose kar dunga")

    assert analysis["risk_score"] >= engine.block_threshold
    assert analysis["label"] == "Threat"
    assert analysis["action"] == "block"


def test_analyze_message_flags_sexual_harassment_phrase():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "0", "score": 0.55}])
    engine.toxicity_model = None

    analysis = engine.analyze_message("private pictures bhejo warna pics viral kar dunga")

    assert analysis["risk_score"] >= engine.flag_threshold
    assert analysis["label"] == "Unsafe"
    assert analysis["action"] == "block"


def test_analyze_message_marks_self_harm_distress_for_escalation_not_safe():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "0", "score": 0.55}])
    engine.toxicity_model = None

    analysis = engine.analyze_message("main khudkushi karna chahta hoon")

    assert analysis["risk_score"] >= engine.flag_threshold
    assert analysis["label"] == "Distress"
    assert analysis["action"] == "flag"


def test_analyze_message_lowers_risk_for_testing_context():
    with patch.dict(os.environ, {}, clear=True):
        engine = AIEngine()

    engine.binary_model = Mock(return_value=[{"label": "0", "score": 0.55}])
    engine.toxicity_model = None

    analysis = engine.analyze_message("ye moderation testing ke liye hai, dekh lunga phrase ko detect karna hai")

    assert analysis["risk_score"] < engine.flag_threshold
    assert analysis["action"] == "allow"
