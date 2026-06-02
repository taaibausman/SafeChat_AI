import fs from "node:fs";
import path from "node:path";

loadDotEnv();

export const config = {
  fastApiUrl: process.env.FASTAPI_URL || "http://127.0.0.1:8000",
  authPath: process.env.WHATSAPP_AUTH_PATH || "./auth",
  controlPort: Number(process.env.WHATSAPP_CONTROL_PORT || 3011),
  monitorRefreshMs: Number(process.env.WHATSAPP_MONITOR_REFRESH_MS || 15000),
  singleAccountMode: parseBoolean(
    process.env.SAFECHAT_WHATSAPP_SINGLE_ACCOUNT_MODE || process.env.WHATSAPP_SINGLE_ACCOUNT_MODE || "0"
  ),
  defaultSessionKey: normalizeSessionKey(
    process.env.SAFECHAT_WHATSAPP_DEMO_SESSION_KEY || process.env.WHATSAPP_DEFAULT_SESSION_KEY || "safechat-demo"
  ),
  forwardAllMessagesInSingleAccountMode: parseBoolean(
    process.env.SAFECHAT_WHATSAPP_AUTO_FORWARD_ALL || process.env.WHATSAPP_AUTO_FORWARD_ALL || "1"
  ),
};

function loadDotEnv() {
  const envPath = path.resolve(process.cwd(), ".env");
  if (!fs.existsSync(envPath)) {
    return;
  }

  const raw = fs.readFileSync(envPath, "utf8");
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex === -1) {
      continue;
    }
    const key = trimmed.slice(0, separatorIndex).trim();
    const value = trimmed.slice(separatorIndex + 1).trim();
    if (!(key in process.env)) {
      process.env[key] = value;
    }
  }
}

function parseBoolean(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function normalizeSessionKey(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "");
  return normalized || "safechat-demo";
}
