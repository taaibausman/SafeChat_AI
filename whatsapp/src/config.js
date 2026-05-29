import fs from "node:fs";
import path from "node:path";

loadDotEnv();

export const config = {
  fastApiUrl: process.env.FASTAPI_URL || "http://127.0.0.1:8000",
  authPath: process.env.WHATSAPP_AUTH_PATH || "./auth",
  controlPort: Number(process.env.WHATSAPP_CONTROL_PORT || 3011),
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
