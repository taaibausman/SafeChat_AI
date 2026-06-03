import json
import os
from dataclasses import dataclass


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
RULES_CONFIG_PATH = os.path.join(ROOT_DIR, "backend", "config", "roman_urdu_moderation_rules.json")


def _normalize_entries(entries: list[str] | None) -> frozenset[str]:
    if not entries:
        return frozenset()
    cleaned = {
        str(entry).strip().lower()
        for entry in entries
        if str(entry).strip()
    }
    return frozenset(cleaned)


def _sorted_phrases(values: frozenset[str]) -> tuple[str, ...]:
    return tuple(sorted(values, key=len, reverse=True))


@dataclass(frozen=True)
class CompiledModerationRules:
    safe_tokens: frozenset[str]
    scam_phrases: tuple[str, ...]
    threat_phrases: tuple[str, ...]
    harassment_phrases: tuple[str, ...]
    self_harm_phrases: tuple[str, ...]
    sexual_harassment_phrases: tuple[str, ...]
    blackmail_phrases: tuple[str, ...]
    distress_phrases: tuple[str, ...]
    safe_context_phrases: tuple[str, ...]
    negation_context_phrases: tuple[str, ...]
    abuse_tokens: frozenset[str]
    threat_tokens: frozenset[str]
    sexual_tokens: frozenset[str]
    safe_context_tokens: frozenset[str]


def load_compiled_moderation_rules() -> CompiledModerationRules:
    with open(RULES_CONFIG_PATH, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    categories = payload.get("categories", {})
    safe_markers = categories.get("safe_conversation_markers", {})
    negation_markers = categories.get("negation_context_markers", {})

    safe_tokens = _normalize_entries(safe_markers.get("tokens", [])) | _normalize_entries([
        "aao", "acha", "achi", "allah", "ao", "assalam", "bolo", "btao", "btado", "class",
        "dua", "good", "haan", "han", "hello", "help", "hi", "ho", "hun", "inshallah",
        "jaa", "kal", "kaise", "kaisi", "kaisay", "kahan", "kab", "kar", "kr", "kia", "kya",
        "kidhar", "kesi", "meeting", "notes", "okay", "ok", "pdf", "please", "raha", "rahe",
        "rahi", "salam", "scene", "send", "share", "shukria", "thank", "thanks", "theek",
        "thik", "thk", "timing", "walaikum", "waiting", "yaar",
    ])

    scam_phrases = _normalize_entries(categories.get("scams_fraud", {}).get("strong_phrases", [])) | _normalize_entries([
        "send money", "gift card", "crypto", "password", "otp", "bank details",
        "account number", "easy paisa", "easypaisa", "jazzcash", "share your code",
        "verification code", "wire transfer", "payment screenshot",
    ])
    threat_phrases = _normalize_entries(categories.get("threats_violence", {}).get("strong_phrases", [])) | _normalize_entries([
        "kill you", "beat you", "destroy you", "i will ruin your life", "i will find you",
        "regret this", "you will regret this",
    ])
    harassment_phrases = _normalize_entries(categories.get("harassment_stalking", {}).get("strong_phrases", [])) | _normalize_entries(
        categories.get("abuse_insults", {}).get("strong_phrases", [])
    ) | _normalize_entries([
        "shut up", "nobody cares", "go to hell", "get lost", "you are useless",
        "you are stupid", "you are disgusting", "hate you",
    ])
    self_harm_phrases = _normalize_entries(categories.get("self_harm_encouragement", {}).get("strong_phrases", [])) | _normalize_entries([
        "go kill yourself", "kill yourself", "you should disappear",
    ])
    sexual_harassment_phrases = _normalize_entries(categories.get("sexual_harassment", {}).get("strong_phrases", []))
    blackmail_phrases = _normalize_entries(categories.get("blackmail_extortion", {}).get("strong_phrases", []))
    distress_phrases = _normalize_entries(categories.get("self_harm_distress_safe_to_escalate", {}).get("strong_phrases", []))
    safe_context_phrases = _normalize_entries(safe_markers.get("phrases", []))
    negation_context_phrases = _normalize_entries(negation_markers.get("phrases", []))

    abuse_tokens = _normalize_entries(categories.get("abuse_insults", {}).get("tokens", [])) | _normalize_entries([
        "stupid", "useless", "idiot", "loser", "hate",
    ])
    threat_tokens = _normalize_entries(categories.get("threats_violence", {}).get("tokens", [])) | _normalize_entries([
        "kill", "destroy", "regret",
    ])
    sexual_tokens = _normalize_entries(categories.get("sexual_harassment", {}).get("tokens", []))
    safe_context_tokens = _normalize_entries(safe_markers.get("tokens", [])) | _normalize_entries(
        negation_markers.get("tokens", [])
    )

    return CompiledModerationRules(
        safe_tokens=safe_tokens,
        scam_phrases=_sorted_phrases(scam_phrases),
        threat_phrases=_sorted_phrases(threat_phrases),
        harassment_phrases=_sorted_phrases(harassment_phrases),
        self_harm_phrases=_sorted_phrases(self_harm_phrases),
        sexual_harassment_phrases=_sorted_phrases(sexual_harassment_phrases),
        blackmail_phrases=_sorted_phrases(blackmail_phrases),
        distress_phrases=_sorted_phrases(distress_phrases),
        safe_context_phrases=_sorted_phrases(safe_context_phrases),
        negation_context_phrases=_sorted_phrases(negation_context_phrases),
        abuse_tokens=abuse_tokens,
        threat_tokens=threat_tokens,
        sexual_tokens=sexual_tokens,
        safe_context_tokens=safe_context_tokens,
    )
