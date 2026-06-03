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
const DIRECTORY_CACHE_REFRESH_MS = 60000;

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
      directoryCache: {
        contacts: new Map(),
        chats: new Map(),
        groups: new Map(),
        refreshedAt: 0,
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

function cleanJid(value) {
  return String(value || "").split("@")[0].split(":")[0];
}

function normalizeActivityTimestamp(value) {
  const numeric = Number(value || 0);
  if (!numeric) {
    return null;
  }
  return numeric > 1e12 ? numeric : numeric * 1000;
}

function directPhoneNumber(value) {
  const normalized = cleanJid(value);
  return /^\d+$/.test(normalized) ? normalized : null;
}

function upsertDirectoryContact(session, contact) {
  const key = cleanJid(contact?.id || contact?.jid || contact?.lid);
  if (!key) {
    return;
  }
  const current = session.directoryCache.contacts.get(key) || {};
  session.directoryCache.contacts.set(key, {
    ...current,
    chat_key: key,
    display_name: contact?.name || contact?.notify || contact?.verifiedName || current.display_name || key,
    phone_number: directPhoneNumber(contact?.id || contact?.jid) || current.phone_number || null,
    source: current.source || "contact",
  });
}

function upsertDirectoryChat(session, chat) {
  const key = cleanJid(chat?.id || chat?.jid || chat?.conversationTimestamp);
  if (!key) {
    return;
  }
  const isGroup = String(chat?.id || chat?.jid || "").endsWith("@g.us");
  const current = session.directoryCache.chats.get(key) || {};
  session.directoryCache.chats.set(key, {
    ...current,
    chat_key: key,
    chat_type: isGroup ? "group" : "direct",
    display_name: chat?.name || chat?.conversationName || current.display_name || key,
    phone_number: isGroup ? null : (directPhoneNumber(chat?.id || chat?.jid) || current.phone_number || null),
    source: current.source || "recent",
    last_activity_at:
      normalizeActivityTimestamp(chat?.conversationTimestamp || chat?.lastMessageRecvTimestamp) || current.last_activity_at || null,
    recent_message_count: current.recent_message_count || 0,
  });
}

function upsertDirectoryGroup(session, groupMetadata) {
  const key = cleanJid(groupMetadata?.id);
  if (!key) {
    return;
  }
  const current = session.directoryCache.groups.get(key) || {};
  session.directoryCache.groups.set(key, {
    ...current,
    chat_key: key,
    chat_type: "group",
    display_name: groupMetadata?.subject || current.display_name || key,
    phone_number: null,
    source: "group",
    last_activity_at:
      normalizeActivityTimestamp(groupMetadata?.creation) || current.last_activity_at || null,
    recent_message_count: current.recent_message_count || 0,
  });
}

function noteMessageActivity(session, message) {
  const key = cleanJid(message?.group_id);
  if (!key) {
    return;
  }
  const current = session.directoryCache.chats.get(key) || {
    chat_key: key,
    chat_type: message?.chat_type || "direct",
    display_name: message?.group_name || message?.sender_name || key,
    phone_number: message?.chat_type === "direct" ? directPhoneNumber(key) : null,
    source: "recent",
    recent_message_count: 0,
    last_activity_at: null,
  };
  current.display_name =
    message?.chat_type === "group"
      ? message?.group_name || current.display_name || key
      : message?.sender_name || message?.group_name || current.display_name || key;
  current.chat_type = message?.chat_type || current.chat_type || "direct";
  current.phone_number =
    current.chat_type === "direct" ? directPhoneNumber(message?.sender || key) || current.phone_number || null : null;
  current.source = current.source || "recent";
  current.recent_message_count = Number(current.recent_message_count || 0) + 1;
  current.last_activity_at = normalizeActivityTimestamp(message?.timestamp) || Date.now();
  session.directoryCache.chats.set(key, current);

  if (current.chat_type === "direct") {
    upsertDirectoryContact(session, {
      id: message?.sender,
      name: message?.sender_name,
      notify: message?.sender_name,
    });
  }
}

async function refreshChatDirectory(sessionKey, force = false) {
  const resolvedSessionKey = resolveSessionKey(sessionKey);
  const session = getSession(resolvedSessionKey);
  if (!session?.socket) {
    return;
  }
  const age = Date.now() - Number(session.directoryCache.refreshedAt || 0);
  if (!force && age < DIRECTORY_CACHE_REFRESH_MS) {
    return;
  }
  try {
    const groups = await session.socket.groupFetchAllParticipating();
    for (const groupMetadata of Object.values(groups || {})) {
      upsertDirectoryGroup(session, groupMetadata);
    }
    session.directoryCache.refreshedAt = Date.now();
  } catch (error) {
    console.warn("Could not refresh WhatsApp chat directory:", error.message);
  }
}

function buildDirectoryResponse(session, search = "", limit = 40) {
  const monitoredKeys = new Set(
    (session.monitoredContactsCache.contacts || []).map((contact) => `${contact.chat_type || "direct"}:${normalizeKey(contact.chat_key)}`)
  );
  const merged = new Map();

  for (const entry of session.directoryCache.contacts.values()) {
    merged.set(`direct:${entry.chat_key}`, {
      chat_key: entry.chat_key,
      chat_type: "direct",
      display_name: entry.display_name || entry.chat_key,
      phone_number: entry.phone_number || null,
      source: entry.source || "contact",
      recent_message_count: 0,
      last_activity_at: entry.last_activity_at || null,
    });
  }
  for (const entry of session.directoryCache.chats.values()) {
    const cacheKey = `${entry.chat_type || "direct"}:${entry.chat_key}`;
    const current = merged.get(cacheKey) || {};
    merged.set(cacheKey, {
      ...current,
      chat_key: entry.chat_key,
      chat_type: entry.chat_type || current.chat_type || "direct",
      display_name: entry.display_name || current.display_name || entry.chat_key,
      phone_number: entry.phone_number || current.phone_number || null,
      source: entry.source || current.source || "recent",
      recent_message_count: Math.max(Number(current.recent_message_count || 0), Number(entry.recent_message_count || 0)),
      last_activity_at: entry.last_activity_at || current.last_activity_at || null,
    });
  }
  for (const entry of session.directoryCache.groups.values()) {
    const cacheKey = `group:${entry.chat_key}`;
    const current = merged.get(cacheKey) || {};
    merged.set(cacheKey, {
      ...current,
      chat_key: entry.chat_key,
      chat_type: "group",
      display_name: entry.display_name || current.display_name || entry.chat_key,
      phone_number: null,
      source: "group",
      recent_message_count: Math.max(Number(current.recent_message_count || 0), Number(entry.recent_message_count || 0)),
      last_activity_at: current.last_activity_at || entry.last_activity_at || null,
    });
  }

  const query = String(search || "").trim().toLowerCase();
  const items = Array.from(merged.values())
    .filter((entry) => {
      if (!query) {
        return true;
      }
      return [entry.display_name, entry.chat_key, entry.phone_number, entry.source]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    })
    .map((entry) => ({
      ...entry,
      is_monitored: monitoredKeys.has(`${entry.chat_type || "direct"}:${normalizeKey(entry.chat_key)}`),
      last_activity_at: entry.last_activity_at ? new Date(entry.last_activity_at).toISOString() : null,
    }))
    .sort((a, b) => {
      const countDiff = Number(b.recent_message_count || 0) - Number(a.recent_message_count || 0);
      if (countDiff !== 0) {
        return countDiff;
      }
      const timeDiff =
        new Date(b.last_activity_at || 0).getTime() - new Date(a.last_activity_at || 0).getTime();
      if (timeDiff !== 0) {
        return timeDiff;
      }
      return String(a.display_name || "").localeCompare(String(b.display_name || ""));
    });

  return {
    total: items.length,
    items: items.slice(0, limit),
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
  sock.ev.on("messaging-history.set", ({ chats = [], contacts = [] }) => {
    contacts.forEach((contact) => upsertDirectoryContact(session, contact));
    chats.forEach((chat) => upsertDirectoryChat(session, chat));
  });
  sock.ev.on("contacts.upsert", (contacts = []) => {
    contacts.forEach((contact) => upsertDirectoryContact(session, contact));
  });
  sock.ev.on("contacts.update", (contacts = []) => {
    contacts.forEach((contact) => upsertDirectoryContact(session, contact));
  });
  sock.ev.on("chats.upsert", (chats = []) => {
    chats.forEach((chat) => upsertDirectoryChat(session, chat));
  });
  sock.ev.on("chats.update", (chats = []) => {
    chats.forEach((chat) => upsertDirectoryChat(session, chat));
  });
  sock.ev.on("groups.upsert", (groups = []) => {
    groups.forEach((groupMetadata) => upsertDirectoryGroup(session, groupMetadata));
  });
  sock.ev.on("groups.update", (groups = []) => {
    groups.forEach((groupMetadata) => upsertDirectoryGroup(session, groupMetadata));
  });

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
      void refreshChatDirectory(resolvedSessionKey, true);
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
      noteMessageActivity(session, normalized);

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

    if (req.method === "GET" && url.pathname === "/directory") {
      if (!sessionKey) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "session_key is required" }));
        return;
      }
      const session = getSession(sessionKey);
      await refreshChatDirectory(sessionKey, false);
      const limit = Number(url.searchParams.get("limit") || 40);
      const search = url.searchParams.get("search") || "";
      const directory = buildDirectoryResponse(session, search, Number.isFinite(limit) ? limit : 40);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          ok: true,
          session_key: sessionKey,
          status: session.bridgeState.status,
          detail: session.bridgeState.detail,
          ...directory,
        })
      );
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
