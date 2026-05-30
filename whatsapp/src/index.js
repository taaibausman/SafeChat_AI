import http from "node:http";

import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";
import qrcode from "qrcode-terminal";
import { Server as SocketIOServer } from "socket.io";

import { config } from "./config.js";
import { normalizeIncomingMessage } from "./message-normalizer.js";

let currentSocket = null;
let isRestarting = false;
let reconnectDelayMs = 3000;
let socketServer = null;
let bridgeState = {
  status: "starting",
  detail: "Bridge booting",
  monitored_contacts: 0,
};
let monitoredContactsCache = {
  contacts: [],
  fetchedAt: 0,
};

function emitBridgeEvent(type, payload) {
  socketServer?.emit(type, payload);
}

function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "");
}

function currentBridgeSnapshot() {
  return {
    ...bridgeState,
    monitored_contacts: monitoredContactsCache.contacts.length,
    socket_transport: "socket.io",
  };
}

async function postStatus(status, reason = null, qr = null, connectedPhone = null) {
  bridgeState = {
    ...bridgeState,
    status,
    detail: reason,
    qr,
    connected_phone: connectedPhone,
  };
  emitBridgeEvent("bridge_status", currentBridgeSnapshot());

  try {
    await fetch(`${config.fastApiUrl}/api/whatsapp/status`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status, reason, qr, connected_phone: connectedPhone }),
    });
  } catch (error) {
    console.warn("Could not post WhatsApp status to FastAPI:", error.message);
  }
}

async function sendIncomingMessage(message) {
  try {
    const response = await fetch(`${config.fastApiUrl}/api/whatsapp/messages/incoming`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(message),
    });
    if (!response.ok) {
      throw new Error(`FastAPI returned ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.warn("Could not send WhatsApp message to FastAPI:", error.message);
    emitBridgeEvent("bridge_error", {
      type: "message_forward_failed",
      detail: error.message,
      message_id: message.message_id || null,
      chat_key: message.group_id || null,
    });
    return null;
  }
}

async function fetchMonitoredContacts(force = false) {
  const age = Date.now() - monitoredContactsCache.fetchedAt;
  if (!force && age < config.monitorRefreshMs) {
    return monitoredContactsCache.contacts;
  }

  try {
    const response = await fetch(`${config.fastApiUrl}/api/whatsapp/monitored-contacts?active_only=true`);
    if (!response.ok) {
      throw new Error(`FastAPI returned ${response.status}`);
    }
    const payload = await response.json();
    monitoredContactsCache = {
      contacts: Array.isArray(payload.contacts) ? payload.contacts : [],
      fetchedAt: Date.now(),
    };
    bridgeState = {
      ...bridgeState,
      monitored_contacts: monitoredContactsCache.contacts.length,
    };
    emitBridgeEvent("monitored_contacts", {
      total: monitoredContactsCache.contacts.length,
      contacts: monitoredContactsCache.contacts,
    });
    return monitoredContactsCache.contacts;
  } catch (error) {
    console.warn("Could not refresh monitored contacts:", error.message);
    emitBridgeEvent("bridge_error", {
      type: "monitor_refresh_failed",
      detail: error.message,
    });
    return monitoredContactsCache.contacts;
  }
}

async function shouldForwardMessage(message) {
  const contacts = await fetchMonitoredContacts(false);
  if (!contacts.length) {
    return true;
  }

  const messageKeys = new Set(
    [
      message.group_id,
      message.sender,
      message.group_name,
      message.sender_name,
    ]
      .map(normalizeKey)
      .filter(Boolean)
  );
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
    return monitorKeys.some((key) => messageKeys.has(key));
  });
}

async function restartBridge(reason = "Restart requested from control server.") {
  if (isRestarting) {
    return;
  }

  isRestarting = true;
  bridgeState = { ...bridgeState, status: "restarting", detail: reason };
  emitBridgeEvent("bridge_status", currentBridgeSnapshot());

  try {
    if (currentSocket?.end) {
      currentSocket.end(new Error(reason));
    }
  } catch (error) {
    console.warn("Could not close existing WhatsApp socket cleanly:", error.message);
  }

  setTimeout(() => {
    startWhatsApp().catch((error) => {
      console.error("Failed to restart WhatsApp bridge:", error);
    });
  }, 300);
}

async function startWhatsApp() {
  if (isRestarting) {
    isRestarting = false;
  }

  await fetchMonitoredContacts(true);
  await postStatus("starting", "Connecting to WhatsApp", null);
  bridgeState = { ...bridgeState, status: "starting", detail: "Connecting to WhatsApp" };
  const { state, saveCreds } = await useMultiFileAuthState(config.authPath);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    auth: state,
    version,
    printQRInTerminal: false,
    syncFullHistory: false,
  });

  currentSocket = sock;
  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.log("Scan this QR code with WhatsApp.");
      qrcode.generate(qr, { small: true });
      postStatus("qr_required", "Scan the QR code in WhatsApp Linked Devices.", qr);
    }

    if (connection === "connecting") {
      postStatus("connecting", "Opening WhatsApp session.", null);
    }

    if (connection === "open") {
      console.log("WhatsApp connection established.");
      reconnectDelayMs = 3000;
      postStatus("connected", "Bridge connected.", null, sock.user?.id || null);
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
      postStatus("disconnected", reason, null);

      if (shouldReconnect && !isRestarting) {
        const nextDelay = reconnectDelayMs;
        reconnectDelayMs = Math.min(reconnectDelayMs * 2, 30000);
        setTimeout(() => {
          startWhatsApp().catch((error) => {
            console.error("Failed to restart WhatsApp bridge:", error);
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

      const shouldForward = await shouldForwardMessage(normalized);
      if (!shouldForward) {
        emitBridgeEvent("message_skipped", {
          reason: "unmonitored_chat",
          chat_key: normalized.group_id,
          chat_type: normalized.chat_type,
          message_id: normalized.message_id || null,
        });
        continue;
      }

      const result = await sendIncomingMessage(normalized);
      if (!result || result.duplicate) {
        continue;
      }

      emitBridgeEvent("moderation_result", {
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
    if (req.method === "GET" && req.url === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(currentBridgeSnapshot()));
      return;
    }

    if (req.method === "POST" && req.url === "/restart") {
      await restartBridge();
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, status: "restarting" }));
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
    socket.emit("bridge_status", currentBridgeSnapshot());
    socket.emit("monitored_contacts", {
      total: monitoredContactsCache.contacts.length,
      contacts: monitoredContactsCache.contacts,
    });
  });

  server.listen(config.controlPort, "127.0.0.1", () => {
    console.log(`WhatsApp control server listening on 127.0.0.1:${config.controlPort}`);
  });
}

startControlServer();
startWhatsApp().catch((error) => {
  console.error("WhatsApp bridge crashed during startup:", error);
  process.exitCode = 1;
});

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
  if (message.includes("EACCES")) {
    return "Baileys could not reach WhatsApp Web over HTTPS/WebSocket. Check firewall, proxy, VPN, or network policy.";
  }
  if (message.includes("ENOTFOUND")) {
    return "WhatsApp Web host could not be resolved. Check DNS or internet access.";
  }
  if (message.includes("ETIMEDOUT")) {
    return "Connection to WhatsApp Web timed out. Check internet connectivity.";
  }
  return statusCode ? `Connection interrupted (code ${statusCode}). Reconnecting.` : "Connection lost. Reconnecting.";
}
