import os, sys, json, threading, queue, re, shutil, subprocess, time, tempfile, string
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP = 'MuzikKes'
BASE = Path(__file__).resolve().parent
FFMPEG_BIN = BASE / 'ffmpeg-bin'
PYROOT = Path(sys.executable).parent
DLL_DIRS = [FFMPEG_BIN, PYROOT, PYROOT / 'DLLs', PYROOT / 'Lib' / 'site-packages' / 'torch' / 'lib']
_DLL_HANDLES = []
for _dll_dir in DLL_DIRS:
    if _dll_dir.is_dir():
        os.environ['PATH'] = str(_dll_dir) + os.pathsep + os.environ.get('PATH', '')
        try: _DLL_HANDLES.append(os.add_dll_directory(str(_dll_dir)))
        except (AttributeError, OSError): pass
CFG = BASE / 'settings.json'
DESKTOP = Path.home() / 'Desktop'
DEFAULTS = {'output_dir': str(Path('E:/MuzikKes/Çıktılar') if Path('E:/').exists() else DESKTOP / 'MuzikKes'), 'min_minutes': 1.5, 'max_minutes': 10, 'sample_rate': 48000, 'channels': 2, 'bit_depth': 24, 'format': 'pcm_s24le'}

def load_cfg():
    try: return {**DEFAULTS, **json.loads(CFG.read_text(encoding='utf-8'))}
    except Exception: return DEFAULTS.copy()
def save_cfg(c): CFG.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding='utf-8')
def safe(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', str(s)).strip(' .')
    return re.sub(r'\s+', ' ', s)[:100] or 'Muzik'
def run(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, **kw)
def source_code(url):
    host = urlparse(url).netloc.lower()
    if 'youtube' in host or 'youtu.be' in host: return 'Y'
    if 'facebook' in host or 'fb.watch' in host: return 'F'
    return None
def keyword_from(title):
    ignored={'official','video','audio','music','song','full','version','original','soundtrack','lyrics','youtube','facebook','hd','4k'}
    words=re.findall(r'[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+', title)
    meaningful=[w for w in words if len(w)>2 and w.casefold() not in ignored]
    return safe((meaningful[-1] if meaningful else (words[0] if words else 'Muzik'))).replace(' ','')[:24]
def alpha_suffix(n):
    out=''
    while n:
        n,rem=divmod(n-1,26); out=chr(65+rem)+out
    return out

def batch_for(out):
    out.mkdir(parents=True,exist_ok=True)
    prefix=datetime.now().strftime('%d-%m-%Y')+' '
    folders=sorted((p for p in out.iterdir() if p.is_dir() and p.name.startswith(prefix)),key=lambda p:p.name)
    if folders:
        last=folders[-1]
        if len(list(last.rglob('*.wav')))<12: return last
        letter=last.name[len(prefix):]
        idx=0
        for ch in letter: idx=idx*26+ord(ch.upper())-64
        name=prefix+alpha_suffix(idx+1)
    else: name=prefix+'A'
    p=out/name;p.mkdir(parents=True,exist_ok=True);return p

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('MuzikKes • Akıllı ses çıkarma'); self.geometry('1180x860'); self.minsize(980,740)
        self.cfg=load_cfg(); self.jobs=queue.Queue(); self.busy=False; self.stop_flag=False; self.queue_urls=[]; self.queue_state={}; self._ui(); self.after(150,self._poll)
    def _ui(self):
        self.configure(bg='#111827'); style=ttk.Style(self); style.theme_use('clam')
        style.configure('.',background='#111827',foreground='#e5e7eb',fieldbackground='#1f2937',font=('Segoe UI',10)); style.configure('TButton',padding=7)
        style.configure('TLabel',background='#111827',foreground='#e5e7eb'); style.configure('TLabelframe',background='#111827',foreground='#cbd5e1'); style.configure('TLabelframe.Label',background='#111827',foreground='#55d6c2',font=('Segoe UI',10,'bold'))
        style.configure('TNotebook',background='#111827',borderwidth=0); style.configure('TNotebook.Tab',background='#18232e',foreground='#aab8c5',padding=(18,10)); style.map('TNotebook.Tab',background=[('selected','#173b3a')],foreground=[('selected','#8de8d8')])
        style.configure('Treeview',background='#1b2530',fieldbackground='#1b2530',foreground='#e5e7eb',rowheight=28); style.configure('Treeview.Heading',background='#263441',foreground='#dce6ee',font=('Segoe UI',9,'bold')); style.map('Treeview',background=[('selected','#1d4ed8')])
        head=ttk.Frame(self,padding=(18,14));head.pack(fill='x');ttk.Label(head,text='MuzikKes',font=('Segoe UI',23,'bold')).pack(anchor='w');ttk.Label(head,text='Müzik bölümlerini bul, bağlantılarını sıraya al ve WAV olarak kaydet.',foreground='#91a1af').pack(anchor='w',pady=(2,0))
        self.status=ttk.Label(head,text='●  Hazır',foreground='#71d9b1');self.status.pack(anchor='e')
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=16,pady=(0,14))
        self.search_tab=ttk.Frame(self.tabs,padding=14);self.manual_tab=ttk.Frame(self.tabs,padding=14);self.tabs.add(self.search_tab,text='Video ara');self.tabs.add(self.manual_tab,text='Manuel bağlantılar')
        self._search_ui();self._manual_ui()
    def _search_ui(self):
        f=self.search_tab
        provider=ttk.Frame(f);provider.pack(fill='x',pady=(0,8));ttk.Label(provider,text='Kaynak').pack(side='left');self.provider=tk.StringVar(value='YouTube');ttk.Combobox(provider,textvariable=self.provider,values=['YouTube','Facebook'],state='readonly',width=16).pack(side='left',padx=8);ttk.Label(provider,text='API bağlantısı daha sonra eklenecek',foreground='#e3bd70').pack(side='right')
        q=ttk.LabelFrame(f,text='Video / müzik / sanatçı / kanal',padding=9);q.pack(fill='x',pady=5);self.query=tk.StringVar();self.search_entry=ttk.Entry(q,textvariable=self.query);self.search_entry.pack(side='left',fill='x',expand=True,padx=(0,8));self.search_entry.bind('<Return>',lambda e:self.search());ttk.Button(q,text='Ara',command=self.search).pack(side='left')
        filters=ttk.LabelFrame(f,text='Detaylı arama filtreleri',padding=9);filters.pack(fill='x',pady=5)
        self.filter_vars={}
        items=[('Sıralama','Alaka düzeyi',['Alaka düzeyi','Tarih','Görüntülenme','Puan','Başlık']),('Yayın tarihi','Herhangi',['Herhangi','Son 24 saat','Bu hafta','Bu ay','Özel aralık']),('Süre','Herhangi',['Herhangi','Kısa (<4 dk)','Orta (4–20 dk)','Uzun (>20 dk)']),('Bölge','Tümü',['Tümü','TR','US','GB','DE']),('Dil','Tümü',['Tümü','Türkçe','İngilizce']),('Kategori','Tümü',['Tümü','Müzik','Film','Eğitim']),('Lisans','Herhangi',['Herhangi','Creative Commons']),('Kalite','Herhangi',['Herhangi','HD','Altyazılı'])]
        for i,(label,default,values) in enumerate(items):
            cell=ttk.Frame(filters);cell.grid(row=i//4,column=i%4,sticky='ew',padx=5,pady=4);filters.columnconfigure(i%4,weight=1);ttk.Label(cell,text=label,foreground='#91a1af').pack(anchor='w');v=tk.StringVar(value=default);self.filter_vars[label]=v;ttk.Combobox(cell,textvariable=v,values=values,state='readonly').pack(fill='x',pady=(2,0))
        dates=ttk.Frame(filters);dates.grid(row=2,column=0,columnspan=4,sticky='ew',padx=5,pady=(7,0));ttk.Label(dates,text='Özel yayın tarihi:').pack(side='left');self.after_var=tk.StringVar();ttk.Entry(dates,textvariable=self.after_var,width=14).pack(side='left',padx=5);ttk.Label(dates,text='ile').pack(side='left');self.before_var=tk.StringVar();ttk.Entry(dates,textvariable=self.before_var,width=14).pack(side='left',padx=5);ttk.Label(dates,text='(YYYY-AA-GG)  ·  Çıkarma için: 1,5–10 dk',foreground='#91a1af').pack(side='left',padx=8)
        result=ttk.LabelFrame(f,text='Arama sonuçları',padding=8);result.pack(fill='both',expand=True,pady=5);self.result_tree=ttk.Treeview(result,columns=('title','channel','verified','date','duration','views','quality'),show='headings',height=10)
        for col,label,width in [('title','Video',260),('channel','Kanal',150),('verified','Doğrulama',120),('date','Yayın tarihi',110),('duration','Süre',75),('views','Görüntülenme',110),('quality','Detay',150)]:self.result_tree.heading(col,text=label);self.result_tree.column(col,width=width,anchor='w')
        self.result_tree.pack(fill='both',expand=True);self.result_tree.bind('<Double-1>',lambda e:self._add_selected_result());
        bottom=ttk.Frame(f);bottom.pack(fill='x',pady=(5,0));ttk.Label(bottom,text='YouTube: API ile sayfalı arama ve metadata. Facebook sonuçları API izinlerine bağlıdır.').pack(side='left');ttk.Button(bottom,text='Seçilenleri kuyruğa ekle',command=self._add_selected_result).pack(side='right')
    def _manual_ui(self):
        f=self.manual_tab
        top=ttk.Frame(f);top.pack(fill='x',pady=(0,8));left=ttk.LabelFrame(top,text='Video bağlantıları · her satıra bir URL',padding=9);left.pack(side='left',fill='both',expand=True);right=ttk.LabelFrame(top,text='İşlem kuyruğu',padding=9);right.pack(side='left',fill='both',expand=True,padx=(10,0))
        self.urls=tk.Text(left,height=5,bg='#0b1117',fg='#e5e7eb',insertbackground='white',relief='flat',wrap='none',font=('Consolas',10));self.urls.pack(fill='both',expand=True);actions=ttk.Frame(left);actions.pack(fill='x',pady=(6,0));ttk.Button(actions,text='Panodan yapıştır',command=self.paste).pack(side='left');ttk.Button(actions,text='Kuyruğa ekle',command=self.add_urls).pack(side='left',padx=6);ttk.Button(actions,text='Metni temizle',command=lambda:self.urls.delete('1.0','end')).pack(side='left')
        self.queue_tree=ttk.Treeview(right,columns=('source','state'),show='headings',height=5);self.queue_tree.heading('source',text='Bağlantı');self.queue_tree.heading('state',text='Durum');self.queue_tree.column('source',width=320);self.queue_tree.column('state',width=110);self.queue_tree.pack(fill='both',expand=True)
        row=ttk.Frame(right);row.pack(fill='x',pady=(6,0));ttk.Button(row,text='Seçileni kaldır',command=self.remove_selected).pack(side='left');self.startbtn=ttk.Button(row,text='Kuyruğu işle',command=self.start);self.startbtn.pack(side='right');self.stopbtn=ttk.Button(row,text='Durdur',command=self.stop,state='disabled');self.stopbtn.pack(side='right',padx=6)
        opts=ttk.LabelFrame(f,text='Kesim ve WAV · çıktı düzeni',padding=9);opts.pack(fill='x',pady=5)
        self.vars={k:tk.StringVar(value=str(self.cfg[k])) for k in ('min_minutes','max_minutes','sample_rate','channels','bit_depth')}
        for label,key,vals in [('En kısa (dk)','min_minutes',['1','1.5','2','3','5']),('En uzun (dk)','max_minutes',['3','5','8','10']),('Örnekleme (Hz)','sample_rate',['22050','44100','48000','96000']),('Kanal','channels',['1','2']),('Bit','bit_depth',['16','24','32'])]:
            cell=ttk.Frame(opts);cell.pack(side='left',padx=(0,12));ttk.Label(cell,text=label,foreground='#91a1af').pack(anchor='w');ttk.Combobox(cell,textvariable=self.vars[key],values=vals,width=12,state='readonly').pack(anchor='w',pady=3)
        out=ttk.Frame(opts);out.pack(fill='x',pady=(8,0));ttk.Label(out,text='Kayıt klasörü').pack(side='left');self.outvar=tk.StringVar(value=self.cfg['output_dir']);ttk.Entry(out,textvariable=self.outvar).pack(side='left',fill='x',expand=True,padx=8);ttk.Button(out,text='Seç…',command=self.pick).pack(side='left');ttk.Label(out,text='Her klasörde 12 parça · aynı URL kesitleri kaynak alt klasöründe',foreground='#71d9b1').pack(side='left',padx=10)
        pane=ttk.LabelFrame(f,text='İşlem günlüğü',padding=8);pane.pack(fill='both',expand=True,pady=5);self.log=tk.Text(pane,bg='#0b1220',fg='#d1d5db',insertbackground='white',relief='flat',state='disabled',wrap='word',height=9);self.log.pack(fill='both',expand=True)
        self.say('Hazır. Bağlantıları alt alta ekleyin; arama API’leri yapılandırıldığında sonuçlar ilk sekmede görünecek.')
    def paste(self):
        try:self.urls.insert('insert',self.clipboard_get())
        except tk.TclError:self.say('Pano boş veya metin içermiyor.')
    def add_urls(self):
        raw=[u.strip() for u in self.urls.get('1.0','end').splitlines() if u.strip()];added=0
        for url in raw:
            code=source_code(url)
            if not code:self.say(f'Atlandı: desteklenmeyen bağlantı biçimi: {url}');continue
            if url in self.queue_urls:self.say(f'Tekrarlanan bağlantı atlandı: {url}');continue
            self.queue_urls.append(url);self.queue_state[url]='Kuyrukta';self.queue_tree.insert('', 'end',iid=str(len(self.queue_urls)-1),values=(f'{code} · {url}', 'Kuyrukta'));added+=1;self.say(f'Bağlantı kuyruğa eklendi ({code}): {url}')
        if added:self.urls.delete('1.0','end')
    def remove_selected(self):
        for iid in self.queue_tree.selection():
            try:url=self.queue_urls[int(iid)];self.queue_urls[int(iid)]='';self.queue_tree.delete(iid);self.say(f'Kuyruktan kaldırıldı: {url}')
            except (ValueError,IndexError):pass
    def search(self):
        provider=self.provider.get();query=self.query.get().strip()
        if not query:messagebox.showinfo('Arama','Önce bir arama sözü girin.');return
        self.say(f'{provider} arama isteği hazırlandı: {query}')
        if provider=='YouTube':self.say('YouTube Data API anahtarı henüz eklenmedi. API anahtarı eklendiğinde seçili filtrelerle gerçek sonuçlar listelenecek.')
        else:self.say('Facebook araması Meta API erişim izni ve uygulama anahtarı gerektirir. API bağlantısı henüz eklenmedi.')
        messagebox.showinfo('API kurulumu bekleniyor',f'{provider} API ayarları bu sürümde henüz bağlı değil. Arama formu ve filtreler hazır; hesap API bilgileri eklendiğinde gerçek sonuçlar burada listelenecek.')
    def _add_selected_result(self):
        sel=self.result_tree.selection()
        if not sel:self.say('Kuyruğa eklenecek arama sonucu seçin. API bağlantısı gelince sonuç URL’leri burada gösterilecek.');return
        for iid in sel:
            values=self.result_tree.item(iid,'values');self.say('Arama sonucu kuyruğa eklenecek: '+str(values[0]))
    def pick(self):
        p=filedialog.askdirectory(initialdir=self.outvar.get())
        if p:self.outvar.set(p)
    def say(self,s):self.jobs.put(('log',s))
    def stop(self):self.stop_flag=True;self.status.configure(text='Durduruluyor…');self.say('Durdurma istendi; geçerli ses işlemi bitince kuyruk duracak.')
    def start(self):
        if self.busy:return
        urls=[u for u in self.queue_urls if u]
        if not urls:messagebox.showinfo('Kuyruk boş','Önce bir veya daha fazla bağlantı ekleyin.');return
        try:
            c={k:(float(self.vars[k].get()) if k in ('min_minutes','max_minutes') else int(self.vars[k].get())) for k in self.vars}
            if c['min_minutes']<=0 or c['max_minutes']<c['min_minutes']:raise ValueError('Süre aralığını kontrol edin.')
            c.update(output_dir=self.outvar.get().strip(),format='pcm_s%dle'%c['bit_depth'])
            if not c['output_dir']:raise ValueError('Kayıt klasörü seçin.')
        except Exception as e:messagebox.showerror('Ayar hatası',str(e));return
        self.cfg=c;save_cfg(c);self.busy=True;self.stop_flag=False;self.startbtn.configure(state='disabled');self.stopbtn.configure(state='normal');self.status.configure(text='●  Çalışıyor…');threading.Thread(target=self.worker,args=(urls,c),daemon=True).start()
    def queue_update(self,url,state):self.jobs.put(('state',(url,state)))
    def worker(self,urls,c):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.say('HATA: FFmpeg/ffprobe bulunamadı.');self.jobs.put(('done',None));return
        try:import yt_dlp
        except ImportError:self.say('HATA: yt-dlp kurulu değil.');self.jobs.put(('done',None));return
        out=Path(c['output_dir']);out.mkdir(parents=True,exist_ok=True);cache=out.parent/'Gecici';cache.mkdir(parents=True,exist_ok=True)
        for ix,url in enumerate(urls,1):
            if self.stop_flag:break
            self.queue_update(url,'İşleniyor');self.say(f'[{ix}/{len(urls)}] Bilgi alınıyor: {url}')
            try:
                opts={'format':'bestaudio/best','outtmpl':str(cache/'%(id)s.%(ext)s'),'noplaylist':True,'quiet':True,'no_warnings':True,'restrictfilenames':True}
                with yt_dlp.YoutubeDL(opts) as ydl:info=ydl.extract_info(url,download=True)
                file=Path(ydl.prepare_filename(info))
                if not file.exists():
                    matches=list(cache.glob(safe(info.get('id',''))+'.*'));file=matches[0] if matches else file
                if not file.exists():raise RuntimeError('İndirilen ses dosyası bulunamadı.')
                title=safe(info.get('track') or info.get('title') or 'Muzik');code=source_code(url) or 'Y';self.say('Ses indirildi. Müzik bölümleri yerel AI modeliyle taranıyor…')
                segments=self.detect(file,c)
                if not segments:self.say('Uygun uzunlukta müzik bölümü tespit edilmedi.');self.queue_update(url,'Uygun bölüm yok');continue
                batch=batch_for(out);multi=len(segments)>1;group=batch/safe(title) if multi else batch
                if multi:group.mkdir(parents=True,exist_ok=True)
                keyword=keyword_from(title)
                for n,(start,end,score,kind) in enumerate(segments,1):
                    if self.stop_flag:break
                    vocal='SING' if kind=='SING' else 'ENS';suffix='' if n==1 else '-'+alpha_suffix(n)
                    stem=safe(f'{code}-{vocal}-{keyword}{suffix}');wav=group/(stem+'.wav');bump=2
                    while wav.exists():wav=group/(stem+f'-{bump}'+'.wav');bump+=1
                    cmd=['ffmpeg','-y','-ss',f'{start:.2f}','-i',str(file),'-t',f'{end-start:.2f}','-vn','-ac',str(c['channels']),'-ar',str(c['sample_rate']),'-c:a',c['format'],str(wav)]
                    res=run(cmd)
                    if res.returncode:raise RuntimeError(res.stderr[-500:])
                    self.say(f'KAYDEDİLDİ: {wav}  ({start/60:.1f}–{end/60:.1f} dk, AI {score:.0%})')
                self.queue_update(url,'Tamamlandı')
            except Exception as e:self.say(f'HATA: {e}');self.queue_update(url,'Hata')
        self.jobs.put(('done',None))
    def detect(self,path,c):
        # Two-stage batched AudioSet analysis: coarse windows across the audio, then detailed windows only around candidates.
        try:
            import numpy as np, soundfile as sf, torch
            from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
            bundle=getattr(self,'_audio_classifier',None)
            if bundle is None:
                model_id='MIT/ast-finetuned-audioset-10-10-0.4593';extractor=AutoFeatureExtractor.from_pretrained(model_id);model=AutoModelForAudioClassification.from_pretrained(model_id).eval();torch.set_num_threads(max(1,min(8,os.cpu_count() or 4)));bundle=(torch,extractor,model);self._audio_classifier=bundle
            torch,extractor,model=bundle;fd,tmp_name=tempfile.mkstemp(suffix='.wav',dir=str(Path(path).parent));os.close(fd)
            conv=run(['ffmpeg','-y','-i',str(path),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',tmp_name])
            if conv.returncode:raise RuntimeError('FFmpeg ses analizi için dönüştüremedi: '+conv.stderr[-400:])
            sr=16000;win=10;labels_music={'music','musical instrument','singing','song','background music','guitar','piano','drum','bass guitar','synthesizer','violin','organ','folk music','pop music','rock music','hip hop music','electronic music','classical music','jazz','country','blues','music of africa','music of latin america'};labels_speech={'speech','conversation','narration, monologue','male speech, man speaking','female speech, woman speaking','child speech, kid speaking','whispering','shout','yelling'};labels_vocal={'singing','song','choir','vocal music'}
            def is_music(music,speech):return music>=.18 and speech<=.22 and music>=speech*1.25
            def classify(items):
                if not items:return []
                inputs=extractor([chunk for _,chunk in items],sampling_rate=sr,return_tensors='pt',padding=True)
                with torch.inference_mode():probs=torch.softmax(model(**inputs).logits,dim=-1)
                scores=[]
                for i,(start,chunk) in enumerate(items):
                    top=probs[i].topk(min(10,probs.shape[-1]));d={str(model.config.id2label.get(int(idx),model.config.id2label.get(str(int(idx)),''))).lower():float(score) for score,idx in zip(top.values,top.indices)}
                    music=max([v for k,v in d.items() if any(label in k for label in labels_music)] or [0.]);speech=max([v for k,v in d.items() if any(label in k for label in labels_speech)] or [0.]);vocal=max([v for k,v in d.items() if any(label in k for label in labels_vocal)] or [0.]);scores.append((float(start),float(start+len(chunk)/sr),float(music),float(speech),float(vocal)))
                return scores
            def scan(audio_path,offset,hop,stage):
                found=[];batch=[]
                with sf.SoundFile(audio_path) as audio:
                    y=audio.read(dtype='float32',always_2d=True).mean(axis=1);duration=len(y)/sr;total=max(1,int(np.ceil(duration/hop)));self.say(f'{stage}: {total} pencere, {duration/60:.1f} dakika ses')
                    for start in np.arange(0,max(1,duration-win+hop),hop):
                        chunk=y[int(start*sr):int((start+win)*sr)]
                        if len(chunk)<sr*2:continue
                        batch.append((float(start),chunk))
                        if len(batch)>=16:
                            found.extend(classify(batch));batch=[]
                            if len(found) and len(found)%32<16:self.say(f'{stage}: {min(len(found),total)}/{total} pencere')
                    found.extend(classify(batch))
                return [(s+offset,e+offset,m,sp,v) for s,e,m,sp,v in found]
            try:
                with sf.SoundFile(tmp_name) as audio:duration=len(audio)/sr
                if duration<1:return []
                coarse=scan(tmp_name,0,20,'Hızlı tarama');positives=[(s,e) for s,e,m,sp,v in coarse if is_music(m,sp)];candidates=[]
                for s,e in positives:
                    if candidates and s<=candidates[-1][1]+30:candidates[-1]=(candidates[-1][0],e)
                    else:candidates.append((s,e))
                candidates=[(max(0,s-10),min(duration,e+10)) for s,e in candidates];self.say(f'{len(candidates)} geçici müzik adayı bulundu; ayrıntılı tarama başlıyor');refined=[]
                for i,(start,end) in enumerate(candidates,1):
                    fd,candidate_path=tempfile.mkstemp(suffix='.wav',dir=str(Path(path).parent));os.close(fd)
                    try:
                        with sf.SoundFile(tmp_name) as source_audio:
                            source_audio.seek(int(start*sr));data=source_audio.read(int((end-start)*sr),dtype='float32',always_2d=True)
                        with sf.SoundFile(candidate_path,'w',samplerate=sr,channels=1,subtype='PCM_16') as dst:dst.write(data)
                        self.say(f'Aday {i}/{len(candidates)} ayrıntılı inceleniyor ({start/60:.1f}–{end/60:.1f} dk)');refined.extend(scan(candidate_path,start,5,f'Aday {i}'))
                    finally:
                        try:os.unlink(candidate_path)
                        except OSError:pass
            finally:
                try:os.unlink(tmp_name)
                except OSError:pass
            runs=[]
            for s,e,score,speech,vocal in refined:
                if is_music(score,speech):
                    if runs and s<=runs[-1][1]+4:runs[-1]=(runs[-1][0],e,max(runs[-1][2],score),max(runs[-1][3],vocal))
                    else:runs.append((s,e,score,vocal))
            minsec=c['min_minutes']*60;maxsec=c['max_minutes']*60;out=[]
            for s,e,score,vocal in runs:
                if e-s<minsec:continue
                while e-s>maxsec:out.append((s,s+maxsec,score,'SING' if vocal>=.15 else 'ENS'));s+=maxsec
                if e-s>=minsec:out.append((s,e,score,'SING' if vocal>=.15 else 'ENS'))
            return out
        except Exception as e:raise RuntimeError('AI ses analizi başarısız: '+str(e))
    def _poll(self):
        try:
            while True:
                kind,msg=self.jobs.get_nowait()
                if kind=='log':
                    self.log.configure(state='normal');self.log.insert('end',datetime.now().strftime('%H:%M:%S')+'  '+msg+'\n');self.log.see('end');self.log.configure(state='disabled')
                elif kind=='state':
                    url,state=msg
                    for iid in self.queue_tree.get_children():
                        vals=self.queue_tree.item(iid,'values')
                        if url in str(vals[0]):self.queue_tree.set(iid,'state',state);break
                else:
                    self.busy=False;self.startbtn.configure(state='normal');self.stopbtn.configure(state='disabled');self.status.configure(text='●  Durduruldu' if self.stop_flag else '●  Tamamlandı')
        except queue.Empty:pass
        self.after(150,self._poll)

if __name__=='__main__':App().mainloop()


