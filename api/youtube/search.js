const YOUTUBE_API = "https://www.googleapis.com/youtube/v3";

function parseDuration(value = "") {
  const m = value.match(/^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/);
  if (!m) return 0;
  return Number(m[1] || 0) * 3600 + Number(m[2] || 0) * 60 + Number(m[3] || 0);
}

function isoDate(value, end = false) {
  if (!value) return "";
  const date = new Date(`${value}T${end ? "23:59:59" : "00:00:00"}Z`);
  return Number.isNaN(date.valueOf()) ? "" : date.toISOString();
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "Yalnızca POST desteklenir." });
  }
  const key = process.env.YOUTUBE_API_KEY;
  if (!key) return res.status(503).json({ error: "YouTube API anahtarı sunucuda ayarlı değil." });

  const body = req.body || {};
  const q = String(body.q || "").trim().slice(0, 200);
  if (!q) return res.status(400).json({ error: "Arama sözü gerekli." });

  const params = new URLSearchParams({
    part: "snippet",
    type: "video",
    q,
    maxResults: "25",
    order: ["relevance", "date", "viewCount", "rating"].includes(body.order) ? body.order : "relevance",
    key,
  });
  const publishedAfter = isoDate(body.publishedAfter);
  const publishedBefore = isoDate(body.publishedBefore, true);
  if (publishedAfter) params.set("publishedAfter", publishedAfter);
  if (publishedBefore) params.set("publishedBefore", publishedBefore);
  if (["short", "medium", "long"].includes(body.videoDuration)) params.set("videoDuration", body.videoDuration);
  if (/^[A-Z]{2}$/.test(body.regionCode || "")) params.set("regionCode", body.regionCode);
  if (/^[a-z]{2}(-[A-Z]{2})?$/.test(body.relevanceLanguage || "")) params.set("relevanceLanguage", body.relevanceLanguage);
  if (body.videoCategoryId && /^\d+$/.test(body.videoCategoryId)) params.set("videoCategoryId", body.videoCategoryId);
  if (["any", "creativeCommon"].includes(body.videoLicense)) params.set("videoLicense", body.videoLicense);
  if (["any", "high", "standard"].includes(body.videoDefinition) && body.videoDefinition !== "any") params.set("videoDefinition", body.videoDefinition);
  if (["any", "closedCaption", "none"].includes(body.videoCaption) && body.videoCaption !== "any") params.set("videoCaption", body.videoCaption);

  try {
    const searchResponse = await fetch(`${YOUTUBE_API}/search?${params}`);
    const searchData = await searchResponse.json();
    if (!searchResponse.ok) {
      const reason = searchData?.error?.errors?.[0]?.reason;
      const message = searchData?.error?.message || "YouTube arama isteği başarısız.";
      return res.status(searchResponse.status === 403 ? 429 : searchResponse.status).json({ error: message, reason });
    }

    const ids = (searchData.items || []).map((item) => item.id?.videoId).filter(Boolean);
    if (!ids.length) return res.status(200).json({ items: [], nextPageToken: searchData.nextPageToken || null });

    const detailParams = new URLSearchParams({
      part: "contentDetails,statistics,snippet",
      id: ids.join(","),
      key,
    });
    const detailResponse = await fetch(`${YOUTUBE_API}/videos?${detailParams}`);
    const detailData = await detailResponse.json();
    if (!detailResponse.ok) return res.status(502).json({ error: detailData?.error?.message || "Video ayrıntıları alınamadı." });
    const details = new Map((detailData.items || []).map((item) => [item.id, item]));

    const items = (searchData.items || []).map((item) => {
      const id = item.id?.videoId;
      const d = details.get(id) || {};
      const seconds = parseDuration(d.contentDetails?.duration);
      return {
        id,
        url: `https://www.youtube.com/watch?v=${id}`,
        title: item.snippet?.title || "Başlıksız video",
        description: item.snippet?.description || "",
        channelTitle: item.snippet?.channelTitle || "",
        channelId: item.snippet?.channelId || "",
        publishedAt: item.snippet?.publishedAt || "",
        thumbnail: item.snippet?.thumbnails?.medium?.url || item.snippet?.thumbnails?.default?.url || "",
        durationSeconds: seconds,
        duration: d.contentDetails?.duration || "",
        viewCount: d.statistics?.viewCount || null,
        categoryId: d.snippet?.categoryId || "",
        // YouTube Data API v3 does not expose the channel verification badge.
        channelVerified: null,
      };
    });
    return res.status(200).json({ items, nextPageToken: searchData.nextPageToken || null });
  } catch (error) {
    return res.status(502).json({ error: "YouTube API'ye bağlanılamadı." });
  }
}
