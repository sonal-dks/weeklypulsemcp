const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const { Client } = require("@modelcontextprotocol/sdk/client/index.js");
const { StdioClientTransport } = require("@modelcontextprotocol/sdk/client/stdio.js");

function json(res, status, body) {
  res.status(status).setHeader("Content-Type", "application/json");
  res.send(JSON.stringify(body));
}

function parseRecipients(input) {
  if (Array.isArray(input)) {
    return [...new Set(input.map((x) => String(x || "").trim()).filter(Boolean))];
  }
  return [...new Set(String(input || "").split(/[,\n;]+/).map((x) => x.trim()).filter(Boolean))];
}

function isValidEmail(email) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email);
}

async function ensureGmailCredentialsPath() {
  const existingPath = (process.env.GMAIL_CREDENTIALS_PATH || "").trim();
  if (existingPath) {
    try {
      await fs.access(existingPath);
      return existingPath;
    } catch {
      // continue and try materialization
    }
  }

  const b64 = (process.env.GMAIL_CREDENTIALS_JSON_B64 || "").trim();
  const raw = (process.env.GMAIL_CREDENTIALS_JSON || "").trim();
  let jsonText = "";

  if (b64) {
    try {
      jsonText = Buffer.from(b64, "base64").toString("utf8");
    } catch {
      throw new Error("Invalid GMAIL_CREDENTIALS_JSON_B64.");
    }
  } else if (raw) {
    jsonText = raw;
  } else {
    throw new Error("Missing Gmail credentials. Set GMAIL_CREDENTIALS_JSON_B64 in Vercel.");
  }

  try {
    JSON.parse(jsonText);
  } catch {
    throw new Error("Invalid Gmail credentials JSON.");
  }

  const target = path.join(os.tmpdir(), "gmail-credentials.json");
  await fs.writeFile(target, jsonText, "utf8");
  process.env.GMAIL_CREDENTIALS_PATH = target;
  return target;
}

async function fetchJson(baseUrl, relativePath) {
  const response = await fetch(`${baseUrl}${relativePath}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : response.statusText;
    throw new Error(`Upstream ${relativePath} failed: ${detail}`);
  }
  return data;
}

async function sendViaGmailMcp({ to, subject, htmlBody }) {
  const gmailPath = await ensureGmailCredentialsPath();
  const transport = new StdioClientTransport({
    command: process.env.GOOGLE_GMAIL_MCP_COMMAND || "npx",
    args: ["-y", process.env.GOOGLE_GMAIL_MCP_PACKAGE || "@gongrzhe/server-gmail-autoauth-mcp"],
    env: {
      ...process.env,
      GMAIL_CREDENTIALS_PATH: gmailPath,
      PYTHONUNBUFFERED: "1",
    },
  });

  const client = new Client({ name: "weeklypulsemcp-deliver", version: "1.0.0" });
  await client.connect(transport);
  try {
    const out = await client.callTool({
      name: "send_email",
      arguments: {
        to: [to],
        subject,
        body: htmlBody,
        mimeType: "text/html",
      },
    });
    if (out && out.isError) {
      throw new Error("Gmail MCP send_email returned error.");
    }
  } finally {
    await client.close().catch(() => {});
  }
}

module.exports = async (req, res) => {
  if (req.method !== "POST") {
    return json(res, 405, { detail: "Method not allowed" });
  }

  try {
    const {
      recipients,
      fund_names = [],
      delivery_token = "",
      week: requestedWeek = "",
    } = req.body || {};

    const expectedToken = (process.env.DELIVERY_TRIGGER_TOKEN || "").trim();
    if (!expectedToken) {
      return json(res, 500, { detail: "Delivery token is not configured." });
    }
    if (String(delivery_token).trim() !== expectedToken) {
      return json(res, 403, { detail: "Token wrong. Please get token from admin." });
    }

    const toList = parseRecipients(recipients);
    if (!toList.length) {
      return json(res, 400, { detail: "At least one recipient is required" });
    }
    const bad = toList.filter((e) => !isValidEmail(e));
    if (bad.length) {
      return json(res, 400, { detail: `Invalid email(s): ${bad.join(", ")}` });
    }

    const proto = req.headers["x-forwarded-proto"] || "https";
    const host = req.headers["x-forwarded-host"] || req.headers.host;
    const baseUrl = `${proto}://${host}`;

    let week = String(requestedWeek || "").trim();
    if (!week) {
      const weeks = await fetchJson(baseUrl, "/api/weeks");
      week = (weeks.weeks && weeks.weeks[0]) || "";
      if (!week) {
        throw new Error("No weeks available to deliver.");
      }
    }

    const pulse = await fetchJson(baseUrl, `/api/pulse/${encodeURIComponent(week)}`);
    const fundNamesCsv = Array.isArray(fund_names) ? fund_names.join(",") : "";
    const fee = await fetchJson(
      baseUrl,
      `/api/preview/fee?fund_names=${encodeURIComponent(fundNamesCsv)}&week=${encodeURIComponent(week)}`
    );

    const subject = `Groww Weekly Product Pulse - ${week}`;
    const pulseEsc = String(pulse.markdown || "").replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
    const feeEsc = String(fee.text || "None selected.").replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
    const docId = (process.env.GOOGLE_DOC_ID || "").trim();
    const docUrl = docId ? `https://docs.google.com/document/d/${docId}/edit` : "";
    const htmlBody = `
      <div style="font-family:Arial,sans-serif;line-height:1.55;color:#0f172a">
        <h2 style="margin:0 0 10px 0">Weekly Groww Product Pulse - ${week}</h2>
        <pre style="white-space:pre-wrap;background:#f8fafc;padding:12px;border:1px solid #e2e8f0;border-radius:8px">${pulseEsc}</pre>
        <h3 style="margin:16px 0 8px 0">Fee Explainer</h3>
        <pre style="white-space:pre-wrap;background:#f8fafc;padding:12px;border:1px solid #e2e8f0;border-radius:8px">${feeEsc}</pre>
        ${docUrl ? `<p><a href="${docUrl}">Open Google Doc</a></p>` : ""}
      </div>
    `;

    for (const recipient of toList) {
      await sendViaGmailMcp({ to: recipient, subject, htmlBody });
    }

    return json(res, 200, {
      ok: true,
      week,
      recipients: toList,
      doc_url: docUrl,
      message: "Sent email to each recipient.",
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    console.error("[deliver-node] error:", detail);
    return json(res, 502, { detail });
  }
};

