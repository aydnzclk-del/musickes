# MuzikKes

MuzikKes has two parts: a static Vercel web interface and a Windows/Python processing worker. The web interface can collect and show search/manual queue details. FFmpeg downloads, AudioSet analysis, and WAV export run on the Windows VDS; Vercel does not process long audio jobs.

## Current state

- The desktop worker is the working processing program. It uses FFmpeg/ffprobe, yt-dlp and a local AudioSet AST model.
- The Vercel site is a UI shell. YouTube/Facebook API search and remote worker control are not connected yet.
- API credentials must be stored on the worker/server as protected environment settings; never commit them to GitHub or put them in browser JavaScript.
- A later backend link will require an authenticated HTTPS endpoint from Vercel to the VDS and job status/output routes.

## Desktop use

Open `app.py`, paste authorized YouTube/Facebook links in **Manuel bağlantılar**, choose the duration and WAV settings, and run the queue. Default minimum is 1.5 minutes, maximum 10 minutes. Analysis is a prediction, so listen to saved cuts.

## Disk layout

On the current VDS, the unallocated space on the 240 GB virtual disk was formatted as an NTFS `E:` volume labelled `MuzikKes`. The project directories are:

- `E:\\MuzikKes\\Uygulama` — portable source and requirements for migration.
- `E:\\MuzikKes\\Gecici` — downloaded audio and temporary analysis files.
- `E:\\MuzikKes\\Çıktılar` — dated output batches and WAV clips.

Each dated batch holds up to 12 clips; extra clips from the same source are grouped under a source-title folder. Names follow `Y-SING-keyword.wav` / `F-ENS-keyword.wav`; additional clips from one source use `-B`, `-C`, and so on. The app falls back to Desktop storage if `E:` does not exist on a future host.

## Requirements and migration

Install Python 3.10+, FFmpeg/ffprobe, then `pip install -r requirements.txt`. The first analysis downloads the AST model. For a new host, copy `Uygulama`, install the requirements and FFmpeg, then point `output_dir` to that host's data drive. Keep `Gecici` and `Çıktılar` out of Git.

## Search API setup (later)

- YouTube Data API v3 can provide video search and metadata. The channel verified badge is not directly exposed as a standard Data API field.
- Facebook discovery is limited by Meta API product permissions and app review; it does not expose a general public video search to every app.
- Add provider keys only after obtaining them from the account owner. Keep them in local settings or server-side secrets, not source files.

## Vercel deployment

Vercel serves the static `index.html`. The page currently saves the manual queue in that browser only and shows that search/processing are not connected. The VDS worker API, authentication, secure HTTPS route, and persistent cross-device queue remain to be implemented before remote processing can be enabled.

