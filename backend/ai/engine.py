import os
import threading
import torch

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
        self.disable_models = bool(os.environ.get("SAFECHAT_DISABLE_MODELS", ""))
        self.flag_threshold = float(os.environ.get("SAFECHAT_FLAG_THRESHOLD", "55"))
        self.block_threshold = float(os.environ.get("SAFECHAT_BLOCK_THRESHOLD", "85"))

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
                model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "best_model")
                if os.path.isdir(model_path):
                    try:
                        # import transformers pipeline lazily
                        from transformers import pipeline as _pipeline
                        self.binary_model = _pipeline("text-classification", model=model_path, tokenizer=model_path, device=self.device)
                    except Exception as e:
                        print(f"Warning: Could not load custom model from {model_path}. Error: {e}")
                        self.binary_model = None
                else:
                    print(f"Custom binary model path not found: {model_path}. Skipping custom model.")
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
                # Assuming labels are like LABEL_0 and LABEL_1 or safe/unsafe
                if binary_label == 'unsafe' or binary_label == 'label_1' or binary_label == '1':
                    binary_score = res['score']
                else:
                    binary_score = 1.0 - res['score']
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
        rule_score = 0
        rule_label = None
        text_lower = text.lower()
        if any(word in text_lower for word in ["send money", "gift card", "crypto", "password"]):
            rule_score = 0.8
            rule_label = "Scam"
        elif any(word in text_lower for word in ["kill", "destroy", "beat you"]):
            rule_score = 0.9
            rule_label = "Threat"

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
                "binary_score": binary_score,
                "toxicity": tox_results
            }
        }

# Singleton instance
ai_engine = AIEngine()
