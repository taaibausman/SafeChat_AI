import os
import threading
import re
import torch
from backend.ai.rule_loader import load_compiled_moderation_rules


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
RULES = load_compiled_moderation_rules()


def _env_flag(name: str) -> bool:
    value = (os.environ.get(name) or "").strip().lower()
    return value not in {"", "0", "false", "no", "off"}


# Lazy load models to speed up initial server start
class AIEngine:
    def __init__(self):
        self.device = 0 if torch.cuda.is_available() else -1
        self.binary_model = None
        self.toxicity_model = None
        self.emotion_model = None
        self.models_loaded = False
        self.models_loading = False
        self._load_lock = threading.Lock()
        self.disable_models = _env_flag("SAFECHAT_DISABLE_MODELS")
        self.flag_threshold = float(os.environ.get("SAFECHAT_FLAG_THRESHOLD", "55"))
        self.block_threshold = float(os.environ.get("SAFECHAT_BLOCK_THRESHOLD", "85"))
        self.custom_model_path = self._resolve_custom_model_path()

    def _resolve_custom_model_path(self) -> str | None:
        configured = (os.environ.get("SAFECHAT_CUSTOM_MODEL_PATH") or "").strip()
        candidate_paths = []
        if configured:
            candidate_paths.append(
                configured if os.path.isabs(configured) else os.path.join(ROOT_DIR, configured)
            )
        candidate_paths.extend(
            [
                os.path.join(ROOT_DIR, "classifier"),
                os.path.join(ROOT_DIR, "best_model"),
            ]
        )

        seen: set[str] = set()
        for candidate in candidate_paths:
            normalized = os.path.abspath(candidate)
            if normalized in seen:
                continue
            seen.add(normalized)
            if os.path.isdir(normalized):
                return normalized
        return None

    def _is_unsafe_binary_label(self, label: str | None) -> bool:
        normalized = str(label or "").strip().lower()
        return normalized in {"unsafe", "label_1", "1", "true", "toxic", "harmful"}

    def _tokenize_text(self, text: str) -> list[str]:
        return re.findall(r"[a-zA-Z']+", str(text or "").lower())

    def _contains_threat_or_abuse_terms(self, text: str) -> bool:
        text_lower = str(text or "").lower()
        phrase_markers = (
            RULES.scam_phrases
            + RULES.threat_phrases
            + RULES.harassment_phrases
            + RULES.self_harm_phrases
            + RULES.sexual_harassment_phrases
            + RULES.blackmail_phrases
            + RULES.distress_phrases
        )
        if any(marker in text_lower for marker in phrase_markers):
            return True

        token_markers = RULES.abuse_tokens | RULES.threat_tokens | RULES.sexual_tokens
        return any(token in token_markers for token in self._tokenize_text(text_lower))

    def _looks_like_benign_short_message(self, text: str) -> bool:
        tokens = self._tokenize_text(text)
        if not tokens or len(tokens) > 4:
            return False
        if self._contains_threat_or_abuse_terms(text):
            return False

        safe_hits = sum(1 for token in tokens if token in RULES.safe_tokens)
        short_text = len(" ".join(tokens)) <= 24
        return short_text and safe_hits >= 1

    def _rule_based_signal(self, text: str) -> tuple[float, str | None]:
        text_lower = str(text or "").lower().strip()
        tokens = set(self._tokenize_text(text_lower))
        safe_context_hits = sum(1 for phrase in RULES.safe_context_phrases if phrase in text_lower)
        negation_context_hits = sum(1 for phrase in RULES.negation_context_phrases if phrase in text_lower)
        safe_context_hits += len(tokens & RULES.safe_context_tokens) // 2
        context_soften = bool(negation_context_hits or safe_context_hits >= 2)

        if any(phrase in text_lower for phrase in RULES.scam_phrases):
            if context_soften:
                return 0.38, "Safe"
            return 0.82, "Scam"
        if any(phrase in text_lower for phrase in RULES.blackmail_phrases):
            if context_soften:
                return 0.45, "Safe"
            return 0.9, "Threat"
        if any(phrase in text_lower for phrase in RULES.sexual_harassment_phrases):
            if context_soften:
                return 0.42, "Safe"
            return 0.86, "Unsafe"
        if any(phrase in text_lower for phrase in RULES.distress_phrases):
            return 0.78, "Distress"
        if any(phrase in text_lower for phrase in RULES.self_harm_phrases):
            if context_soften:
                return 0.45, "Safe"
            return 0.93, "Threat"
        if any(phrase in text_lower for phrase in RULES.threat_phrases):
            if context_soften:
                return 0.44, "Safe"
            return 0.92, "Threat"
        if any(phrase in text_lower for phrase in RULES.harassment_phrases):
            base_score = 0.72
            if context_soften:
                base_score = 0.42
            return base_score, "Unsafe" if base_score >= 0.55 else "Safe"

        abuse_hits = len(tokens & RULES.abuse_tokens)
        threat_hits = len(tokens & RULES.threat_tokens)
        sexual_hits = len(tokens & RULES.sexual_tokens)

        if threat_hits >= 2:
            if context_soften:
                return 0.42, "Safe"
            return 0.88, "Threat"
        if sexual_hits >= 2:
            if context_soften:
                return 0.4, "Safe"
            return 0.76, "Unsafe"
        if abuse_hits >= 2:
            score = 0.7
            if context_soften:
                score = 0.4
            return score, "Unsafe" if score >= 0.55 else "Safe"
        if abuse_hits == 1 and len(tokens) <= 5:
            score = 0.6
            if context_soften:
                score = 0.34
            return score, "Unsafe" if score >= 0.55 else "Safe"

        return 0.0, None

    def action_for_score(self, score: float | int | None) -> str:
        normalized = float(score or 0.0)
        if normalized >= self.block_threshold:
            return "block"
        if normalized >= self.flag_threshold:
            return "flag"
        return "allow"

    def severity_for_score(self, score: float | int | None) -> str:
        normalized = float(score or 0.0)
        if normalized >= self.block_threshold:
            return "High"
        if normalized >= self.flag_threshold:
            return "Medium"
        return "Low"
        
    def _load_models(self):
        if self.models_loaded or self.disable_models:
            return
        with self._load_lock:
            if self.models_loaded or self.models_loading:
                return
            self.models_loading = True

        try:
            if self.binary_model is None:
                print("Loading custom binary model...")
                model_path = self.custom_model_path
                if model_path:
                    try:
                        # import transformers pipeline lazily
                        from transformers import pipeline as _pipeline
                        self.binary_model = _pipeline("text-classification", model=model_path, tokenizer=model_path, device=self.device)
                    except Exception as e:
                        print(f"Warning: Could not load custom model from {model_path}. Error: {e}")
                        self.binary_model = None
                else:
                    print("Custom binary model path not found. Checked SAFECHAT_CUSTOM_MODEL_PATH, classifier/, and best_model/. Skipping custom model.")
                    self.binary_model = None

            if self.toxicity_model is None:
                print("Loading Detoxify model...")
                try:
                    # import Detoxify lazily to avoid import-time failures
                    from detoxify import Detoxify as _Detoxify
                    self.toxicity_model = _Detoxify('original', device='cuda' if self.device == 0 else 'cpu')
                except Exception as e:
                    print(f"Warning: Could not load Detoxify model. Error: {e}")
                    self.toxicity_model = None
                
            if self.emotion_model is None:
                print("Loading Emotion model...")
                try:
                    from transformers import pipeline as _pipeline
                    self.emotion_model = _pipeline("text-classification", model="j-hartmann/emotion-english-distilroberta-base", device=self.device, top_k=None)
                except Exception as e:
                    print(f"Warning: Could not load Emotion model. Error: {e}")
                    self.emotion_model = None

            self.models_loaded = True
        finally:
            self.models_loading = False
            
    def analyze_message(self, text: str) -> dict:
        # If models are disabled via env, return a fast safe default
        if getattr(self, 'disable_models', False):
            return {
                "risk_score": 0.0,
                "label": "Safe",
                "action": "allow",
                "severity": "Low",
                "thresholds": {
                    "flag": self.flag_threshold,
                    "block": self.block_threshold,
                },
                "details": {"note": "models_disabled"},
            }
        # Do not block waiting for models; use available models or fallbacks.
        if not text.strip():
            return {
                "risk_score": 0,
                "label": "Safe",
                "action": "allow",
                "severity": "Low",
                "thresholds": {
                    "flag": self.flag_threshold,
                    "block": self.block_threshold,
                },
                "details": {},
            }
            
        # 1. Custom Binary Model
        binary_score = 0
        binary_label = "safe"
        if self.binary_model:
            try:
                # Truncate text if needed
                res = self.binary_model(text[:512])[0]
                binary_label = res['label'].lower()
                confidence = float(res.get('score', 0.0))
                if self._is_unsafe_binary_label(binary_label):
                    binary_score = confidence
                else:
                    binary_score = 1.0 - confidence
            except Exception:
                pass

        # 2. Detoxify (Toxicity)
        tox_results = {}
        if self.toxicity_model is not None:
            try:
                tox_results = self.toxicity_model.predict(text)
            except Exception:
                tox_results = {}
            
        max_tox = max(tox_results.values()) if tox_results else 0
        
        # 3. Rules Engine
        rule_score, rule_label = self._rule_based_signal(text)

        if (
            binary_score >= 0.8
            and max_tox < 0.35
            and rule_score == 0
            and self._looks_like_benign_short_message(text)
        ):
            binary_score = min(binary_score, 0.24)

        # 4. Final Risk Calculation
        # Aggregate scores (simplified)
        final_score = max(binary_score, max_tox, rule_score) * 100
        
        if rule_label:
            final_label = rule_label
        elif max_tox > 0.7:
            final_label = "Toxic"
        elif final_score > 60:
            final_label = "Unsafe"
        else:
            final_label = "Safe"
            
        action = self.action_for_score(final_score)
        severity = self.severity_for_score(final_score)

        return {
            "risk_score": final_score,
            "label": final_label,
            "action": action,
            "severity": severity,
            "thresholds": {
                "flag": self.flag_threshold,
                "block": self.block_threshold,
            },
            "details": {
                "custom_model_path": self.custom_model_path,
                "binary_label": binary_label,
                "binary_score": binary_score,
                "toxicity": tox_results
            }
        }

# Singleton instance
ai_engine = AIEngine()
