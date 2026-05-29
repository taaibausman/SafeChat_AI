export function normalizeIncomingMessage(eventMessage) {
  const remoteJid = eventMessage.key?.remoteJid;

  if (!remoteJid || eventMessage.key?.fromMe || !eventMessage.message) {
    return null;
  }

  const text = extractText(eventMessage.message);
  if (!text) {
    return null;
  }

  const senderJid = eventMessage.key?.participant || remoteJid;

  return {
    message_id: eventMessage.key?.id,
    group_id: cleanJid(remoteJid),
    group_name: cleanJid(remoteJid),
    sender: cleanJid(senderJid),
    sender_name: eventMessage.pushName || cleanJid(senderJid),
    text,
    timestamp: Number(eventMessage.messageTimestamp || Math.floor(Date.now() / 1000)),
  };
}

function extractText(message) {
  const content = unwrapEphemeral(message);
  return (
    content.conversation ||
    content.extendedTextMessage?.text ||
    content.imageMessage?.caption ||
    content.videoMessage?.caption ||
    content.documentMessage?.caption ||
    content.buttonsResponseMessage?.selectedDisplayText ||
    content.listResponseMessage?.title ||
    ""
  ).trim();
}

function unwrapEphemeral(message) {
  return (
    message.ephemeralMessage?.message ||
    message.viewOnceMessage?.message ||
    message.viewOnceMessageV2?.message ||
    message
  );
}

function cleanJid(jid) {
  return String(jid || "").split("@")[0].split(":")[0];
}
