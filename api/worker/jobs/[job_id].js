const BASE = process.env.MUZIKKES_WORKER_URL;
const TOKEN = process.env.MUZIKKES_WORKER_TOKEN;

module.exports = async function handler(req, res) {
  if (!BASE || !TOKEN) return res.status(503).json({ error: "VDS işçisi henüz bağlanmadı." });
  const jobId = String(req.query?.job_id || "");
  if (!/^[a-f0-9]{32}$/i.test(jobId)) return res.status(400).json({ error: "Geçersiz iş numarası." });
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.setHeader("Allow", "GET, HEAD");
    return res.status(405).json({ error: "Yalnızca GET desteklenir." });
  }

  try {
    const target = new URL(`/jobs/${jobId}`, BASE.endsWith("/") ? BASE : `${BASE}/`);
    const upstream = await fetch(target, {
      method: req.method,
      headers: { authorization: `Bearer ${TOKEN}`, accept: req.headers.accept || "application/json" },
    });
    res.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    if (contentType) res.setHeader("content-type", contentType);
    if (!upstream.body) return res.end();
    const { Readable } = require("node:stream");
    Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    console.error("VDS job status request failed", error);
    return res.status(502).json({ error: "VDS işleme sunucusuna ulaşılamadı." });
  }
};

