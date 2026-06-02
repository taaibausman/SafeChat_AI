import http from "node:http";
import path from "node:path";

import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";
import qrcode from "qrcode-terminal";
import { Server as SocketIOServer } from "socket.io";

import { config } from "./config.js";
import { normalizeIncomingMessage } from "./message-normalizer.js";

const sessions = new Map();
let socketServer = null;

function emitBridgeEvent(type, payload) {
  socketServer?.emit(type, payload);
}

function resolveSessionKey(sessionKey) {
  const normalized = String(sessionKey || "").trim().toLowerCase();
  if (config.singleAccountMode) {
    return config.defaultSessionKey;
  }
  return normalized || null;
}

function getSession(sessionKey) {
  const normalized = resolveSessionKey(sessionKey);
  if (!normalized) {
    return null;
  }
  if (!sessions.has(normalized)) {
    sessions.set(normalized, {
      sessionKey: normalized,
      socket: null,
      isRestarting: false,
      reconnectDelayMs: 3000,
      bridgeState: {
        session_key: normalized,
        status: "idle",
        detail: "Session not started",
        monitored_contacts: 0,
      },
      monitoredContactsCache: {
        contacts: [],
        fetchedAt: 0,
      },
    });
  }
  return sessions.get(normalized);
}

function currentBridgeSnapshot(session) {
  return {
    ...session.bridgeState,
    session_key: session.sessionKey,
    monitored_contacts: session.monitoredContactsCache.contacts.length,
    socket_transport: "socket.io",
  };
}

function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "");
}

function directKeyMatches(messageKey, monitorKey) {
  if (!messageKey || !monitorKey) {
    return false;
  }
  return (
    messageKey === monitorKey ||
    messageKey.endsWith(monitorKey) ||
    monitorKey.endsWith(messageKey)
  );
}

async function postStatus(sessionKey, status, reason = null, qr = null, connectedPhone = null) {
  const resolvedSessionKey = resolveSessionKey(sessionKey);
  const session = getSession(resolvedSessionKey);
  session.bridgeState = {
    ...session.bridgeState,
    session_key: session.sessionKey,
    status,
    detail: reason,
    qr,
    connected_phone: connectedPhone,
  };
  emitBridgeEvent("bridge_status", currentBridgeSnapshot(session));

  try {
    await fetch(`${config.fastApiUrl}/api/whatsapp/status`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        bridge_session_key: session.sessionKey,
        status,
        reason,
        qr,
        connected_phone: connectedPhone,
      }),
    });
  } catch (error) {
    console.warn("Could not post WhatsApp status to FastAPI:", error.message);
  }
}

async function sendIncomingMessage(sessionKey, message) {
  const resolvedSessionKey = resolveSessionKey(sessionKey);
  try {
    const response = await fetch(`${config.fastApiUrl}/api/whatsapp/messages/incoming`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...message,
        bridge_session_key: resolvedSessionKey,
      }),
    });
    if (!response.ok) {
      throw new Error(`FastAPI returned ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.warn("Could not send WhatsApp message to FastAPI:", error.message);
    emitBridgeEvent("bridge_error", {
      session_key: resolvedSessionKey,
      type: "message_forward_failed",
      detail: error.message,
      message_id: message.message_id || null,
      chat_key: message.group_id || null,
    });
    return null;
  }
}

async function fetchMonitoredContacts(sessionKey, force = false) {
  const resolvedSessionKey = resolveSessionKey(sessionKey);
  const session = getSession(resolvedSessionKey);
  const age = Date.now() - session.monitoredContactsCache.fetchedAt;
  if (!force && age < config.monitorRefreshMs) {
    return session.monitoredContactsCache.contacts;
  }

  try {
    const response = await fetch(
      `${config.fastApiUrl}/api/whatsapp/bridge/monitored-contacts?active_only=true&session_key=${encodeURIComponent(resolvedSessionKey)}`
    );
    if (!response.ok) {
      throw new Error(`FastAPI returned ${response.status}`);
    }
    const payload = await response.json();
    session.monitoredContactsCache = {
      contacts: Array.isArray(payload.contacts) ? payload.contacts : [],
      fetchedAt: Date.now(),
    };
    session.bridgeState = {
      ...session.bridgeState,
      monitored_contacts: session.monitoredContactsCache.contacts.length,
    };
    emitBridgeEvent("monitored_contacts", {
      session_key: resolvedSessionKey,
      total: session.monitoredContactsCache.contacts.length,
      contacts: session.monitoredContactsCache.contacts,
    });
    return session.monitoredContactsCache.contacts;
  } catch (error) {
    console.warn("Could not refresh monitored contacts:", error.message);
    emitBridgeEvent("bridge_error", {
      session_key: resolvedSessionKey,
      type: "monitor_refresh_failed",
      detail: error.message,
    });
    return session.monitoredContactsCache.contacts;
  }
}

async function shouldForwardMessage(sessionKey, message) {
  const contacts = await fetchMonitoredContacts(sessionKey, true);
  if (config.singleAccountMode && config.forwardAllMessagesInSingleAccountMode) {
    return true;
  }
  if (!contacts.length) {
    return false;
  }

  const messageKeys = [
    message.group_id,
    message.sender,
    message.group_name,
    message.sender_name,
  ]
    .map(normalizeKey)
    .filter(Boolean);
  const chatType = message.chat_type || "direct";

  return contacts.some((contact) => {
    if (!contact?.is_active) {
      return false;
    }
    if ((contact.chat_type || "direct") !== chatType) {
      return false;
    }
    const monitorKeys = [contact.chat_key, contact.phone_number, contact.contact_name]
      .map(normalizeKey)
      .filter(Boolean);
    return monitorKeys.some((monitorKey) =>
      messageKeys.some((messageKey) =>
        chatType === "direct"
          ? directKeyMatches(messageKey, monitorKey)
          : messageKey === monitorKey
      )
    );
  });
}

async function restartBridge(sessionKey, reason = "Restart requested from control server.") {
  const resolvedSessionKey = resolveSessionKey(sessionKey);
  const session = getSession(resolvedSessionKey);
  if (session.isRestarting) {
    return;
  }

  session.isRestarting = true;
  session.bridgeState = { ...session.bridgeState, status: "restarting", detail: reason };
  emitBridgeEvent("bridge_status", currentBridgeSnapshot(session));

  try {
    if (session.socket?.end) {
      session.socket.end(new Error(reason));
    }
  } catch (error) {
    console.warn("Could not close existing WhatsApp socket cleanly:", error.message);
  }

  setTimeout(() => {
    startWhatsApp(resolvedSessionKey).catch((error) => {
      console.error(`Failed to restart WhatsApp bridge for ${resolvedSessionKey}:`, error);
    });
  }, 300);
}

async function startWhatsApp(sessionKey) {
  const resolvedSessionKey = resolveSessionKey(sessionKey);
  const session = getSession(resolvedSessionKey);
  if (session.isRestarting) {
    session.isRestarting = false;
  }

  await fetchMonitoredContacts(resolvedSessionKey, true);
  await postStatus(resolvedSessionKey, "starting", "Connecting to WhatsApp", null);
  session.bridgeState = { ...session.bridgeState, status: "starting", detail: "Connecting to WhatsApp" };

  const authPath = path.resolve(process.cwd(), config.authPath, resolvedSessionKey);
  const { state, saveCreds } = await useMultiFileAuthState(authPath);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    auth: state,
    version,
    printQRInTerminal: false,
    syncFullHistory: false,
  });

  session.socket = sock;
  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.log(`Scan this QR code with WhatsApp for ${sessionKey}.`);
      qrcode.generate(qr, { small: true });
      postStatus(resolvedSessionKey, "qr_required", "Scan the QR code in WhatsApp Linked Devices.", qr);
    }

    if (connection === "connecting") {
      postStatus(resolvedSessionKey, "connecting", "Opening WhatsApp session.", null);
    }

    if (connection === "open") {
      console.log(`WhatsApp connection established for ${resolvedSessionKey}.`);
      session.reconnectDelayMs = 3000;
      postStatus(resolvedSessionKey, "connected", "Bridge connected.", null, sock.user?.id || null);
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const rawMessage =
        lastDisconnect?.error?.message ||
        lastDisconnect?.error?.data?.message ||
        lastDisconnect?.error?.toString?.() ||
        null;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      const reason = describeDisconnect(statusCode, rawMessage);
      postStatus(resolvedSessionKey, "disconnected", reason, null);

      if (shouldReconnect && !session.isRestarting) {
        const nextDelay = session.reconnectDelayMs;
        session.reconnectDelayMs = Math.min(session.reconnectDelayMs * 2, 30000);
        setTimeout(() => {
          startWhatsApp(resolvedSessionKey).catch((error) => {
            console.error(`Failed to restart WhatsApp bridge for ${resolvedSessionKey}:`, error);
          });
        }, nextDelay);
      }
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (!["notify", "append"].includes(type)) {
      return;
    }

    for (const eventMessage of messages) {
      const normalized = normalizeIncomingMessage(eventMessage, sock.user?.id || null);
      if (!normalized) {
        continue;
      }

      const forward = await shouldForwardMessage(sessionKey, normalized);
      if (!forward) {
        emitBridgeEvent("message_skipped", {
          session_key: resolvedSessionKey,
          reason: session.monitoredContactsCache.contacts.length
            ? "unmonitored_chat"
            : "no_user_scope_configured",
          chat_key: normalized.group_id,
          chat_type: normalized.chat_type,
          message_id: normalized.message_id || null,
        });
        continue;
      }

      const result = await sendIncomingMessage(resolvedSessionKey, normalized);
      if (!result || result.duplicate) {
        continue;
      }

      emitBridgeEvent("moderation_result", {
        session_key: resolvedSessionKey,
        bridge_message: normalized,
        live_message: result.live_message || null,
        chat: result.chat || null,
        duplicate: false,
        label: result.label || null,
        risk_score: result.risk_score ?? null,
      });
    }
  });
}

function startControlServer() {
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url || "/", `http://${req.headers.host || "127.0.0.1"}`);
    const sessionKey = resolveSessionKey(url.searchParams.get("session_key"));

    if (req.method === "GET" && url.pathname === "/health") {
      if (!sessionKey) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "session_key is required" }));
        return;
      }
      const session = getSession(sessionKey);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(currentBridgeSnapshot(session)));
      return;
    }

    if (req.method === "POST" && url.pathname === "/restart") {
      if (!sessionKey) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "session_key is required" }));
        return;
      }
      await restartBridge(sessionKey);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, status: "restarting", session_key: sessionKey }));
      return;
    }

    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "Not found" }));
  });

  socketServer = new SocketIOServer(server, {
    cors: {
      origin: "*",
      methods: ["GET", "POST"],
    },
  });
  socketServer.on("connection", (socket) => {
    for (const session of sessions.values()) {
      socket.emit("bridge_status", currentBridgeSnapshot(session));
      socket.emit("monitored_contacts", {
        session_key: session.sessionKey,
        total: session.monitoredContactsCache.contacts.length,
        contacts: session.monitoredContactsCache.contacts,
      });
    }
  });

  server.listen(config.controlPort, "127.0.0.1", () => {
    console.log(`WhatsApp control server listening on 127.0.0.1:${config.controlPort}`);
  });
}

startControlServer();

function describeDisconnect(statusCode, rawMessage) {
  const message = String(rawMessage || "");
  if (statusCode === DisconnectReason.loggedOut) {
    return "Logged out. Scan the QR code again.";
  }
  if (statusCode === DisconnectReason.restartRequired || message.includes("restart required")) {
    return "WhatsApp requested a session restart. Reconnecting.";
  }
  if (statusCode === DisconnectReason.connectionClosed) {
    return "WhatsApp connection closed. Reconnecting.";
  }
  if (statusCode === DisconnectReason.connectionLost) {
    return "WhatsApp connection lost. Reconnecting.";
  }
  if (statusCode === DisconnectReason.connectionReplaced) {
    return "This WhatsApp session was replaced by another linked device session.";
  }
  if (statusCode === DisconnectReason.timedOut) {
    return "WhatsApp bridge timed out. Reconnecting.";
  }
  return message || "WhatsApp connection closed.";
}
