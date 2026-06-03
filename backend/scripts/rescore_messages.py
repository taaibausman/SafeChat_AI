import argparse
from collections import defaultdict

from backend.ai.engine import ai_engine
from backend.database.config import SessionLocal
import backend.models.domain as models


def _update_message(message: models.Message) -> dict:
    analysis = ai_engine.analyze_message(message.message or message.content or "")
    action = analysis.get("action") or ai_engine.action_for_score(analysis["risk_score"])
    severity = analysis.get("severity") or ai_engine.severity_for_score(analysis["risk_score"])

    message.risk_score = analysis["risk_score"]
    message.toxicity_score = analysis["risk_score"]
    message.label = analysis["label"]
    message.is_flagged = action in {"flag", "block"}

    toxicity = analysis.get("details", {}).get("toxicity", {})
    for log in message.moderation_logs:
        log.toxic = toxicity.get("toxicity", 0.0)
        log.severe_toxic = toxicity.get("severe_toxic", 0.0)
        log.obscene = toxicity.get("obscene", 0.0)
        log.threat = toxicity.get("threat", 0.0)
        log.insult = toxicity.get("insult", 0.0)
        log.identity_hate = toxicity.get("identity_hate", 0.0)
        log.action = action

    if action in {"flag", "block"}:
        if not message.alerts:
            message.alerts.append(
                models.Alert(
                    alert_type=analysis["label"] or "Unsafe",
                    severity=severity,
                    status="open",
                )
            )
        else:
            for alert in message.alerts:
                alert.alert_type = analysis["label"] or alert.alert_type or "Unsafe"
                alert.severity = severity
                alert.status = "open" if action == "block" else "acknowledged"
                if action == "block":
                    alert.resolved_at = None
    else:
        for alert in message.alerts:
            alert.status = "resolved"

    return analysis


def _update_chat_summary(chat: models.Chat) -> None:
    messages = chat.messages
    total_messages = len(messages)
    flagged_messages = sum(1 for message in messages if (message.risk_score or 0) >= ai_engine.flag_threshold)
    total_score = sum(message.risk_score or 0.0 for message in messages)

    chat.message_count = total_messages
    chat.flagged_message_count = flagged_messages
    if messages:
        chat.last_message_at = max(
            (message.timestamp for message in messages if message.timestamp is not None),
            default=chat.last_message_at,
        )

    safe_percentage = ((total_messages - flagged_messages) / total_messages * 100) if total_messages else 100.0
    unsafe_percentage = (flagged_messages / total_messages * 100) if total_messages else 0.0
    overall_score = (total_score / total_messages) if total_messages else 0.0

    summary = f"Found {flagged_messages} unsafe messages out of {total_messages}."
    if chat.analysis_results is None:
        chat.analysis_results = models.AnalysisResult(
            overall_score=overall_score,
            safe_percentage=safe_percentage,
            unsafe_percentage=unsafe_percentage,
            summary=summary,
        )
    else:
        chat.analysis_results.overall_score = overall_score
        chat.analysis_results.safe_percentage = safe_percentage
        chat.analysis_results.unsafe_percentage = unsafe_percentage
        chat.analysis_results.summary = summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Rescore saved messages using the current moderation engine.")
    parser.add_argument("--chat-name", help="Only rescore messages from a specific chat name.")
    parser.add_argument("--chat-id", type=int, help="Only rescore messages from a specific chat id.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(models.Message).join(models.Chat)
        if args.chat_name:
            query = query.filter(models.Chat.chat_name == args.chat_name)
        if args.chat_id is not None:
            query = query.filter(models.Chat.id == args.chat_id)

        messages = query.order_by(models.Message.id.asc()).all()
        touched_chat_ids: set[int] = set()
        counts = defaultdict(int)

        for message in messages:
            old_score = float(message.risk_score or 0.0)
            old_label = message.label or ""
            analysis = _update_message(message)
            touched_chat_ids.add(message.chat_id)
            counts["messages"] += 1
            if round(old_score, 4) != round(float(analysis["risk_score"]), 4) or old_label != analysis["label"]:
                counts["changed"] += 1

        chats = db.query(models.Chat).filter(models.Chat.id.in_(touched_chat_ids)).all() if touched_chat_ids else []
        for chat in chats:
            _update_chat_summary(chat)

        db.commit()
        print(f"rescored_messages={counts['messages']} changed={counts['changed']} chats={len(chats)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
