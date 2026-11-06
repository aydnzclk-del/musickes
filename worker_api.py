import os, sys, json, time, uuid, queue, threading, sqlite3, re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
DATA = Path('E:/MuzikKes') if Path('E:/').exists() else Path.home() / 'MuzikKes'
OUT = DATA / 'Çıktılar'
TMP = DATA / 'Gecici'
DB = DATA / 'data' / 'jobs.sqlite3'
ENV_FILE = BASE / 'worker.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))
TOKEN = os.environ.get('MUZIKKES_WORKER_TOKEN', '')
PUBLIC_URL = os.environ.get('MUZIKKES_PUBLIC_WORKER_URL', '').rstrip('/')
if not TOKEN:
    raise RuntimeError('MUZIKKES_WORKER_TOKEN worker.env dosyasında ayarlanmalı.')

from app import App, load_cfg

app = FastAPI(title='MuzikKes VDS Worker', version='1.0')
stop_event = threading.Event()
engine = App.__new__(App)
engine.jobs = queue.Queue()
engine.stop_flag = False
engine._audio_classifier = None

class JobInput(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    min_minutes: float = Field(default=1.5, ge=1.5, le=10)
    max_minutes: float = Field(default=10, ge=1.5, le=10)
    sample_rate: int = Field(default=48000)
    channels: int = Field(default=2, ge=1, le=2)
    bit_depth: int = Field(default=24)


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    return con

def init_db():
    with connect() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, url TEXT NOT NULL, state TEXT NOT NULL,
          settings TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
          error TEXT, files TEXT NOT NULL DEFAULT '[]')''')
        con.execute('''CREATE TABLE IF NOT EXISTS logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
          created TEXT NOT NULL, message TEXT NOT NULL)''')

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

def auth(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Authorization gerekli')
    if not __import__('hmac').compare_digest(authorization[7:].strip(), TOKEN):
        raise HTTPException(401, 'Yetkisiz')
    return True

def log(job_id, message):
    with connect() as con:
        con.execute('INSERT INTO logs(job_id,created,message) VALUES(?,?,?)',(job_id,now(),str(message)[:4000]))
        con.execute('UPDATE jobs SET updated=? WHERE id=?',(now(),job_id))
    if str(message).startswith('KAYDEDİLDİ:'):
        m=re.search(r'KAYDEDİLDİ:\s*(.+?\.wav)\s{2,}',str(message),re.I)
        if m:
            p=Path(m.group(1).strip())
            try:
                p.resolve().relative_to(OUT.resolve())
                with connect() as con:
                    row=con.execute('SELECT files FROM jobs WHERE id=?',(job_id,)).fetchone()
                    files=json.loads(row['files']) if row else []
                    rel=str(p.resolve().relative_to(OUT.resolve()))
                    if rel not in files:files.append(rel)
                    con.execute('UPDATE jobs SET files=?,updated=? WHERE id=?',(json.dumps(files,ensure_ascii=False),now(),job_id))
            except (ValueError,OSError): pass

def set_state(job_id, state, error=None):
    with connect() as con:con.execute('UPDATE jobs SET state=?,error=?,updated=? WHERE id=?',(state,error,now(),job_id))

def run_one(job_id, url, settings):
    cfg={**load_cfg(), **settings, 'output_dir':str(OUT)}
    engine.stop_flag=False
    engine.say=lambda message: log(job_id,message)
    def state_cb(_url,state):
        if state=='İşleniyor':set_state(job_id,'processing')
        elif state=='Hata':set_state(job_id,'error','İşleme hatası; ayrıntı günlükte.')
        elif state=='Uygun bölüm yok':set_state(job_id,'no_music')
        elif state=='Tamamlandı':set_state(job_id,'completed')
    engine.queue_update=state_cb
    try:
        engine.worker([url],cfg)
        with connect() as con:row=con.execute('SELECT state FROM jobs WHERE id=?',(job_id,)).fetchone()
        if row and row['state']=='pending':set_state(job_id,'completed')
        elif row and row['state']=='processing':set_state(job_id,'completed')
    except Exception as exc:
        log(job_id,'HATA: '+str(exc));set_state(job_id,'error',str(exc)[:1000])

def worker_loop():
    while not stop_event.is_set():
        with connect() as con:
            row=con.execute("SELECT * FROM jobs WHERE state='pending' ORDER BY created LIMIT 1").fetchone()
            if row:
                con.execute("UPDATE jobs SET state='processing',updated=? WHERE id=? AND state='pending'",(now(),row['id']))
        if not row:
            stop_event.wait(2);continue
        try:run_one(row['id'],row['url'],json.loads(row['settings']))
        except Exception as exc:
            log(row['id'],'HATA: '+str(exc));set_state(row['id'],'error',str(exc)[:1000])

@app.on_event('startup')
def startup():
    init_db();OUT.mkdir(parents=True,exist_ok=True);TMP.mkdir(parents=True,exist_ok=True)
    threading.Thread(target=worker_loop,name='muzikkes-queue-worker',daemon=True).start()

@app.on_event('shutdown')
def shutdown():stop_event.set()

@app.get('/health')
def health():return {'ok':True,'service':'MuzikKes VDS worker','disk':'E:' if Path('E:/').exists() else 'fallback'}

@app.post('/jobs',dependencies=[Depends(auth)])
def create_job(payload: JobInput):
    parsed=urlparse(payload.url)
    host=(parsed.hostname or '').lower()
    allowed = ('youtube.com','youtu.be','facebook.com','fb.watch')
    if parsed.scheme not in ('http','https') or not any(host == d or host.endswith('.'+d) for d in allowed):
        raise HTTPException(400,'Yalnızca YouTube veya Facebook video bağlantısı ekleyin.')
    if payload.max_minutes < payload.min_minutes:raise HTTPException(400,'Maksimum süre minimumdan küçük olamaz.')
    if payload.sample_rate not in (22050,44100,48000,96000):raise HTTPException(400,'Desteklenmeyen örnekleme hızı.')
    if payload.bit_depth not in (16,24,32):raise HTTPException(400,'Desteklenmeyen bit derinliği.')
    jid=uuid.uuid4().hex
    settings={'min_minutes':payload.min_minutes,'max_minutes':payload.max_minutes,'sample_rate':payload.sample_rate,'channels':payload.channels,'bit_depth':payload.bit_depth,'format':f'pcm_s{payload.bit_depth}le'}
    with connect() as con:con.execute('INSERT INTO jobs(id,url,state,settings,created,updated) VALUES(?,?,?,?,?,?)',(jid,payload.url,'pending',json.dumps(settings),now(),now()))
    log(jid,'Bağlantı VDS işlem kuyruğuna eklendi.')
    return {'id':jid,'state':'pending'}

@app.get('/jobs',dependencies=[Depends(auth)])
def list_jobs():
    with connect() as con:rows=con.execute('SELECT id,url,state,created,updated,error,files FROM jobs ORDER BY created DESC LIMIT 100').fetchall()
    return {'jobs':[dict(r) for r in rows]}

@app.get('/jobs/{job_id}',dependencies=[Depends(auth)])
def get_job(job_id:str):
    with connect() as con:
        row=con.execute('SELECT id,url,state,created,updated,error,files FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row:raise HTTPException(404,'İş bulunamadı')
        logs=con.execute('SELECT created,message FROM logs WHERE job_id=? ORDER BY id DESC LIMIT 100',(job_id,)).fetchall()
    item=dict(row);stored=json.loads(item['files']);item['logs']=[dict(x) for x in reversed(logs)]
    item['files']=[]
    for index,rel in enumerate(stored):
        exp=int(time.time())+3600
        sig=__import__('hmac').new(TOKEN.encode(),f'{job_id}:{index}:{exp}'.encode(),'sha256').hexdigest()
        item['files'].append({'name':Path(rel).name,'url':f'{PUBLIC_URL}/download/{job_id}/{index}?exp={exp}&sig={sig}' if PUBLIC_URL else ''})
    return item

@app.get('/download/{job_id}/{file_index}')
def download_file(job_id:str,file_index:int,exp:int,sig:str):
    if exp < int(time.time()) or exp > int(time.time())+3600:raise HTTPException(403,'İndirme bağlantısının süresi doldu.')
    expected=__import__('hmac').new(TOKEN.encode(),f'{job_id}:{file_index}:{exp}'.encode(),'sha256').hexdigest()
    if not __import__('hmac').compare_digest(expected,sig):raise HTTPException(403,'Geçersiz imzalı indirme bağlantısı.')
    with connect() as con:row=con.execute('SELECT files FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not row:raise HTTPException(404,'İş bulunamadı')
    files=json.loads(row['files'])
    if file_index<0 or file_index>=len(files):raise HTTPException(404,'Dosya bulunamadı')
    path=(OUT/files[file_index]).resolve()
    try:path.relative_to(OUT.resolve())
    except ValueError:raise HTTPException(400,'Geçersiz dosya yolu')
    if not path.is_file():raise HTTPException(404,'Dosya henüz hazır değil')
    return FileResponse(path,media_type='audio/wav',filename=path.name)

if __name__=='__main__':
    import uvicorn
    uvicorn.run('worker_api:app',host='127.0.0.1',port=8787,workers=1,log_level='info')


