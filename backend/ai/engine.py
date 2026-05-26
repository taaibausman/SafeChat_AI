import os
import torch
from transformers import pipeline
from detoxify import Detoxify

# Lazy load models to speed up initial server start
class AIEngine:
    def __init__(self):
        self.device = 0 if torch.cuda.is_available() else -1
        self.binary_model = None
        self.toxicity_model = None
        self.emotion_model = None
        
    def _load_models(self):
        if self.binary_model is None:
            print("Loading custom binary model...")
            # Path relative to where main.py is run
            model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "best_model")
            try:
                self.binary_model = pipeline("text-classification", model=model_path, tokenizer=model_path, device=self.device)
            except Exception as e:
                print(f"Warning: Could not load custom model from {model_path}. Error: {e}")
                self.binary_model = None

        if self.toxicity_model is None:
            print("Loading Detoxify model...")
            self.toxicity_model = Detoxify('original', device='cuda' if self.device == 0 else 'cpu')
            
        if self.emotion_model is None:
            print("Loading Emotion model...")
            self.emotion_model = pipeline("text-classification", model="j-hartmann/emotion-english-distilroberta-base", device=self.device, top_k=None)
            
    def analyze_message(self, text: str) -> dict:
        self._load_models()
        if not text.strip():
            return {"risk_score": 0, "label": "Safe", "details": {}}
            
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
        try:
            tox_results = self.toxicity_model.predict(text)
        except Exception:
            pass
            
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
            
        return {
            "risk_score": final_score,
            "label": final_label,
            "details": {
                "binary_score": binary_score,
                "toxicity": tox_results
            }
        }

# Singleton instance
ai_engine = AIEngine()
