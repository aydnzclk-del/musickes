# MuzikKes

MuzikKes consists of a Vercel web interface, a Windows VDS worker, and a GitHub source backup. The Vercel Function forwards short authenticated control requests; FFmpeg downloading, AudioSet analysis, and WAV export run on the VDS CPU/RAM.

## Current status

- `index.html` is the Vercel web interface. The manual queue can submit jobs through `/api/worker` when the VDS worker endpoint is online.
- `api/worker/[...path].js` is the server-side Vercel proxy. It reads the worker URL and secret from Vercel Production environment variables.
- `worker_api.py` stores jobs and logs in SQLite on the VDS, then uses the desktop audio worker for processing.
- YouTube Data API v3 search is connected through `api/youtube/search.js`; `YOUTUBE_API_KEY` is stored as a sensitive Vercel Production variable and never sent to the browser or committed to GitHub.
- Facebook general public-video search is not available through a normal developer key. Facebook links can still be queued manually; broader public-content search requires Meta's research access.
- WAV downloads use short-lived signed URLs to avoid routing large audio files through Vercel's response-size limits.

## VDS storage

The current 240 GB virtual disk now has an NTFS `E:` volume with about 200 GiB allocated from the previously unallocated space. The existing C: and recovery partitions were left in place.

- `E:\\MuzikKes\\Uygulama` — Python source, dependencies list, FFmpeg, worker service, and Cloudflare connector.
- `E:\\MuzikKes\\Gecici` — source audio and temporary analysis files.
- `E:\\MuzikKes\\Çıktılar` — date batches and exported WAV clips.
- `E:\\MuzikKes\\data\\jobs.sqlite3` — local persistent job state and log records.

Batch folders use `GG-AA-YYYY A`, `GG-AA-YYYY B`, etc., with at most 12 WAV clips per batch. Multiple clips from one source are grouped into a source-title folder. Names follow `Y-SING-keyword.wav` / `F-ENS-keyword.wav`, with `-B`, `-C`, etc. for later clips from the same URL.

## Run the VDS worker

Install Python 3.13+, FFmpeg/ffprobe, and packages from `requirements.txt`. Set `MUZIKKES_WORKER_TOKEN` in the local `worker.env` file, then run `python worker_api.py`. The service binds only to `127.0.0.1:8787`; do not expose that port directly.

The Vercel project stores `MUZIKKES_WORKER_TOKEN` as a Secret and `MUZIKKES_WORKER_URL` as a server-side setting. The front-end never receives the token. For remote access, use an HTTPS tunnel or a domain with TLS.

## Tunnel status and limits

The current VDS connection uses a Cloudflare Quick Tunnel for the first online handoff. Its `trycloudflare.com` hostname is temporary, has no uptime guarantee, and changes when the tunnel process is restarted. For a stable service, create a named Cloudflare Tunnel and point a domain you control to it, then update `MUZIKKES_WORKER_URL` in Vercel. A stopped tunnel makes remote processing unavailable while leaving the Vercel page and GitHub backup intact.

## Migration

`Uygulama` contains the worker source and FFmpeg executables. To move to another Windows host, install Python and the requirements, copy the `Uygulama` folder, and set a new worker secret. Copy `Gecici`, `Çıktılar`, and `data` only if you need the old cache, WAVs, and queue history. Keep `worker.env`, Vercel secrets, settings, downloaded media, and WAV files out of Git.
