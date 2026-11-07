const BASE = process.env.MUZIKKES_WORKER_URL;
const TOKEN = process.env.MUZIKKES_WORKER_TOKEN;

function videoKey(raw) {
  try {
    const u = new URL(raw);
    const host = u.hostname.toLowerCase().replace(/^www\./, "");
    if (host === "youtu.be") return `Y:${u.pathname.split("/").filter(Boolean)[0] || ""}`;
    if (host === "youtube.com" || host.endsWith(".youtube.com")) {
      const id = u.searchParams.get("v") || u.pathname.match(/^\/(?:shorts|embed|live)\/([^/?]+)/)?.[1];
      if (id) return `Y:${id}`;
    }
    if (host === "facebook.com" || host.endsWith(".facebook.com") || host === "fb.watch") {
      const id = u.searchParams.get("v") || u.pathname.match(/\/(?:videos|reel|reels)\/(?:[^/]+\/)?(\d+)/)?.[1] || (host === "fb.watch" ? u.pathname.split("/").filter(Boolean)[0] : "");
      if (id) return `F:${id}`;
      return `F:${host}${u.pathname.replace(/\/$/, "")}`;
    }
    return `${host}${u.pathname.replace(/\/$/, "")}${u.searchParams.get("v") ? `?v=${u.searchParams.get("v")}` : ""}`;
  } catch { return String(raw || "").trim(); }
}

async function findExisting(target, key) {
  const upstream = await fetch(new URL("/jobs", target), { headers: { authorization: `Bearer ${TOKEN}`, accept: "application/json" } });
  if (!upstream.ok) return null;
  const data = await upstream.json();
  const valid = new Set(["pending", "processing", "completed", "no_music"]);
  return (data.jobs || []).find(job => videoKey(job.url) === key && valid.has(job.state)) || null;
}

module.exports = async function handler(req, res) {
  if (!BASE || !TOKEN) return res.status(503).json({ error: "VDS işçisi henüz bağlanmadı." });
  const original = req.url || "/api/worker";
  const suffix = original.replace(/^\/api\/worker/, "") || "/";
  const target = new URL(suffix, BASE.endsWith("/") ? BASE : BASE + "/");
  const headers = { authorization: `Bearer ${TOKEN}`, accept: req.headers.accept || "application/json" };
  if (req.headers["content-type"]) headers["content-type"] = req.headers["content-type"];
  const options = { method: req.method, headers };
  if (!['GET','HEAD'].includes(req.method)) {
    const chunks = [];
    for await (const chunk of req) chunks.push(Buffer.from(chunk));
    const body = Buffer.concat(chunks);
    if (req.method === "POST" && suffix === "/jobs") {
      try {
        const payload = JSON.parse(body.toString("utf8"));
        const duplicate = await findExisting(new URL("/", BASE.endsWith("/") ? BASE : `${BASE}/`), videoKey(payload.url));
        if (duplicate) return res.status(200).json({ duplicate: true, id: duplicate.id, state: duplicate.state });
      } catch (error) {
        if (error instanceof SyntaxError) return res.status(400).json({ error: "Geçersiz JSON isteği." });
        console.error("Duplicate preflight failed", error);
      }
    }
    options.body = body;
  }
  try {
    const upstream = await fetch(target, options);
    res.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    const disposition = upstream.headers.get("content-disposition");
    if (contentType) res.setHeader("content-type", contentType);
    if (disposition) res.setHeader("content-disposition", disposition);
    if (!upstream.body) return res.end();
    const { Readable } = require("node:stream");
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    console.error("VDS proxy request failed", error);
    res.status(502).json({ error: "VDS işleme sunucusuna ulaşılamadı." });
  }
};
