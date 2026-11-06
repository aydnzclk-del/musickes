const BASE = process.env.MUZIKKES_WORKER_URL;
const TOKEN = process.env.MUZIKKES_WORKER_TOKEN;

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
    options.body = Buffer.concat(chunks);
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

