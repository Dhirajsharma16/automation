import hmac, os, threading
from functools import wraps
from flask import Flask, jsonify, request, session, redirect
from dotenv import load_dotenv
load_dotenv()
from job_engine import discover_jobs, get_jobs, approve_job, mark_posted
from telegram import send_job
app=Flask(__name__); SECRET=os.getenv('AUTOMATION_SECRET',''); ADMIN_USERNAME=os.getenv('ADMIN_USERNAME','admin'); ADMIN_PASSWORD=os.getenv('ADMIN_PASSWORD',''); app.secret_key=os.getenv('FLASK_SECRET_KEY') or SECRET; app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='Lax')
DISCOVERY_LOCK = threading.Lock()
DISCOVERY_STATE = {'running': False, 'result': None, 'error': None}

def require_secret(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        supplied=request.headers.get('X-Automation-Secret','')
        if not SECRET or not hmac.compare_digest(supplied,SECRET): return jsonify({'ok':False,'error':'Unauthorized'}),401
        return fn(*args,**kwargs)
    return wrapper


def require_basic_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'ok': False, 'error': 'Login required'}), 401
        return fn(*args, **kwargs)
    return wrapper

DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TechTis | Sarkari Naukari Admin</title>
<style>
:root{color-scheme:light;--ink:#172033;--muted:#667085;--line:#e7ebf2;--blue:#315efb;--navy:#101b35;--bg:#f4f6fb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.topbar{background:var(--navy);color:#fff;padding:22px max(22px,calc((100% - 1120px)/2));display:flex;align-items:center;justify-content:space-between;gap:16px}
.brand{display:flex;align-items:center;gap:12px}.logo{width:42px;height:42px;border-radius:13px;background:#315efb;display:grid;place-items:center;font-weight:800;font-size:18px}.brand h1{font-size:18px;margin:0}.brand p{margin:2px 0 0;color:#b9c4dc;font-size:12px}
.live{font-size:12px;color:#b7f7d1;background:#173c37;border:1px solid #286454;padding:6px 10px;border-radius:20px}
main{max-width:1120px;margin:28px auto;padding:0 20px 48px}.intro{display:flex;justify-content:space-between;align-items:end;gap:18px;margin-bottom:20px}.intro h2{font-size:24px;margin:0 0 4px;letter-spacing:-.5px}.muted{color:var(--muted);margin:0}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:18px 0}.stat,.panel{background:#fff;border:1px solid var(--line);border-radius:15px;box-shadow:0 3px 12px #15254b08}.stat{padding:18px}.stat-label{color:var(--muted);font-size:12px;font-weight:600}.stat-value{font-size:28px;font-weight:750;letter-spacing:-1px;margin-top:4px}.stat small{color:var(--muted)}
.panel{padding:20px;margin:16px 0}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.panel h3{font-size:16px;margin:0}.actions{display:flex;gap:9px;flex-wrap:wrap}
button{border:0;border-radius:9px;padding:10px 14px;background:var(--blue);color:white;font-weight:650;font-size:13px;cursor:pointer;transition:.15s}button:hover{filter:brightness(.94);transform:translateY(-1px)}button.secondary{background:#eef2ff;color:#3049a5}button:disabled{opacity:.5;cursor:wait;transform:none}
.status{font-size:12px;color:var(--muted);margin:12px 0 0}.hint{font-size:12px;color:#667085;background:#f8f9fc;border:1px dashed #d8deea;border-radius:9px;padding:10px 12px;margin-top:14px}
.job{border-top:1px solid var(--line);padding:15px 0}.job strong{font-size:14px}.job a{color:#315efb;text-decoration:none;font-weight:600;overflow-wrap:anywhere}.job a:hover{text-decoration:underline}.job p{margin:7px 0;color:#475467}.job .status{font-size:12px;color:var(--muted);margin:5px 0 8px}.empty{padding:20px 0;color:var(--muted);font-size:13px}
@media(max-width:650px){.topbar{padding:18px 20px}.intro{display:block}.grid{grid-template-columns:1fr}.panel{padding:16px}.panel-head{align-items:flex-start;flex-direction:column}.actions button{flex:1}}
</style></head><body>
<header class="topbar"><div class="brand"><div class="logo">T</div><div><h1>TechTis · Sarkari Naukari</h1><p>Recruitment intelligence dashboard</p></div></div><div style="display:flex;align-items:center;gap:12px"><span class="live">● System online</span><button class="secondary" style="background:#263653;color:#fff" onclick="logout()">Sign out</button></div></header>
<main>
<div class="intro"><div><h2>Admin overview</h2><p class="muted">Review official job notices and control what gets published to Telegram.</p></div></div>
<div class="grid">
<div class="stat"><div class="stat-label">PENDING REVIEW</div><div class="stat-value" id="pendingCount">—</div><small>Awaiting your approval</small></div>
<div class="stat"><div class="stat-label">APPROVED</div><div class="stat-value" id="approvedCount">—</div><small>Ready to publish</small></div>
<div class="stat"><div class="stat-label">PUBLISHED</div><div class="stat-value" id="postedCount">—</div><small>Sent to Telegram</small></div>
</div>
<section class="panel"><div class="panel-head"><div><h3>Automation controls</h3><p class="muted">Search official sources, refresh the queue, or publish approved notices.</p></div></div>
<div class="actions"><button id="searchBtn" onclick="runSearch()">↻ Search for new jobs</button><button class="secondary" onclick="loadJobs()">Refresh queue</button><button class="secondary" onclick="publishApproved()">Publish approved</button></div>
<p id="message" class="status" role="status" aria-live="polite">Ready. Publishing always requires your approval.</p>
<div class="hint">Password reminder: your login is the TechTis brand name followed by your chosen four-digit code. Keep this hint private.</div>
</section>
<section class="panel"><div class="panel-head"><h3>Pending jobs</h3></div><div id="pending">Loading…</div></section>
<section class="panel"><div class="panel-head"><h3>Approved jobs</h3></div><div id="approved">Loading…</div></section>
<section class="panel"><div class="panel-head"><h3>Recently published</h3></div><div id="posted">Loading…</div></section>
</main>
<script>
const msg=document.getElementById('message');
async function logout(){await fetch('/logout',{method:'POST'});location.href='/login';}
async function api(path,method='GET'){const r=await fetch(path,{method,credentials:'same-origin',headers:{'Accept':'application/json'}});const raw=await r.text();let data;try{data=JSON.parse(raw);}catch(_){throw new Error('Server HTTP '+r.status+': '+raw.slice(0,180).replace(/\\s+/g,' '));}if(!r.ok)throw new Error(data.error||('HTTP '+r.status));return data;}
function say(t){msg.textContent=t;}
function renderList(target,items,canApprove){const el=document.getElementById(target);el.replaceChildren();if(!items.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='Nothing to show here yet.';el.append(empty);return;}for(const j of items){const div=document.createElement('div');div.className='job';const title=document.createElement('strong');title.textContent=j.title;const meta=document.createElement('p');meta.className='status';meta.textContent=(j.source||'Official source')+' · '+(j.published||'Date not listed')+' · '+j.status;const link=document.createElement('a');link.href=j.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='View official notice ↗';div.append(title,meta,link);if(j.summary){const p=document.createElement('p');p.textContent=j.summary;div.append(p);}if(canApprove){const b=document.createElement('button');b.textContent='Approve notice';b.style.marginTop='10px';b.onclick=()=>approve(j.id);div.append(b);}el.append(div);}}
async function runSearch(){const b=document.getElementById('searchBtn');b.disabled=true;say('Search started. Checking official sources…');try{await api('/admin/ui/run','POST');for(let i=0;i<90;i++){await new Promise(resolve=>setTimeout(resolve,2000));const s=await api('/admin/ui/run-status');if(!s.running){if(s.error)say('Search failed: '+s.error);else if(s.result)say('Search complete. Sources checked: '+s.result.sources_checked+', new jobs: '+s.result.new_items+(s.result.errors.length?' | Errors: '+s.result.errors.join('; '):''));else say('Search finished.');await loadJobs();return;}}say('Search is still running. Refresh the queue in a moment.');}catch(e){say(e.message);}finally{b.disabled=false;}}
async function approve(id){say('Approving notice…');try{await api('/admin/ui/approve/'+id,'POST');say('Notice approved.');await loadJobs();}catch(e){say(e.message);}}
async function publishApproved(){if(!confirm('Publish all approved jobs to Telegram?'))return;say('Publishing approved notices…');try{const d=await api('/admin/ui/publish','POST');say('Published: '+d.published_ids.length+(d.failed.length?' | Failed: '+d.failed.length:''));await loadJobs();}catch(e){say(e.message);}}
async function loadJobs(){try{const d=await api('/admin/ui/jobs');const jobs=d.jobs;const pending=jobs.filter(x=>x.status==='pending'),approved=jobs.filter(x=>x.status==='approved'),posted=jobs.filter(x=>x.status==='posted');document.getElementById('pendingCount').textContent=pending.length;document.getElementById('approvedCount').textContent=approved.length;document.getElementById('postedCount').textContent=posted.length;renderList('pending',pending,true);renderList('approved',approved,false);renderList('posted',posted,false);}catch(e){say(e.message);}}
loadJobs();
</script></body></html>"""

LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TechTis Admin Sign in</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:20px;background:linear-gradient(135deg,#101b35,#243d72);font:14px/1.5 system-ui;color:#172033}.card{width:min(100%,410px);background:white;border-radius:20px;padding:34px;box-shadow:0 25px 70px #0005}.brand{display:flex;align-items:center;gap:12px;margin-bottom:28px}.logo{width:44px;height:44px;border-radius:13px;background:#315efb;color:white;display:grid;place-items:center;font-size:20px;font-weight:800}.brand small,.muted{color:#667085}.eyebrow{font-size:11px;letter-spacing:1.5px;color:#315efb;font-weight:800}.card h1{font-size:26px;margin:8px 0}.muted{margin:0 0 24px}.field{display:block;font-weight:650;font-size:12px;margin:15px 0 7px}input{width:100%;padding:13px;border:1px solid #d9dfeb;border-radius:10px;font:inherit}input:focus{outline:2px solid #c7d2fe;border-color:#315efb}button{width:100%;margin-top:20px;padding:13px;border:0;border-radius:10px;background:#315efb;color:white;font-weight:700;cursor:pointer}.error{color:#b42318;font-size:12px;min-height:18px;margin-top:12px}.hint{margin-top:16px;padding:11px;background:#f5f7fb;border-radius:9px;color:#667085;font-size:11px}.foot{text-align:center;color:#98a2b3;font-size:11px;margin-top:22px}</style></head><body><main class="card"><div class="brand"><div class="logo">T</div><div><b>TechTis Admin</b><br><small>Sarkari Naukari control centre</small></div></div><div class="eyebrow">SECURE ACCESS</div><h1>Welcome back</h1><p class="muted">Sign in to manage verified government job alerts.</p><form id="f"><label class="field">Username</label><input name="username" value="admin" autocomplete="username" required><label class="field">Password</label><input name="password" type="password" placeholder="Enter admin password" autocomplete="current-password" required><button>Sign in to dashboard</button><div class="error" id="err"></div></form><div class="hint">Password hint: TechTis brand name + your selected four-digit code.</div><div class="foot">Protected admin area · TechTis.in</div></main><script>document.getElementById('f').addEventListener('submit',async e=>{e.preventDefault();let x=document.getElementById('err');x.textContent='Signing in…';try{let r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(new FormData(e.target))});let d=await r.json();if(!r.ok)throw Error(d.error||'Sign in failed');location.href='/dashboard'}catch(err){x.textContent=err.message}})</script></body></html>"""

@app.get('/login')
def login_page():
    if session.get('admin_logged_in'): return redirect('/dashboard')
    return LOGIN_HTML, 200, {'Content-Type':'text/html; charset=utf-8'}

@app.post('/login')
def login_submit():
    username=request.form.get('username','')
    password=request.form.get('password','')
    expected=ADMIN_PASSWORD or SECRET
    if not expected or username != ADMIN_USERNAME or not hmac.compare_digest(password, expected):
        return jsonify({'ok':False,'error':'Incorrect username or password. Check Render admin settings.'}), 401
    session.clear()
    session['admin_logged_in']=True
    return jsonify({'ok':True})

@app.post('/logout')
def logout():
    session.clear()
    return jsonify({'ok':True})

@app.get('/dashboard')
def dashboard():
    if not session.get('admin_logged_in'): return redirect('/login')
    return DASHBOARD_HTML, 200, {'Content-Type':'text/html; charset=utf-8'}

@app.get('/admin/ui/config')
@require_basic_auth
def ui_config():
    import json
    from pathlib import Path
    path = Path(os.getenv('SOURCES_FILE', 'sources.json'))
    try:
        cfg = json.loads(path.read_text(encoding='utf-8'))
        sources = cfg.get('sources', [])
        return jsonify({'ok': True, 'config_path': str(path), 'sources_configured': len(sources), 'sources_enabled': sum(1 for s in sources if s.get('enabled')), 'source_names': [s.get('name') for s in sources if s.get('enabled')]})
    except Exception as exc:
        app.logger.exception('Source config check failed')
        return jsonify({'ok': False, 'error': f'Source config unavailable: {type(exc).__name__}: {exc}'}), 500

@app.get('/admin/ui/jobs')
@require_basic_auth
def ui_jobs():
    return jsonify({'ok': True, 'jobs': get_jobs(limit=200)})

def _background_discovery():
    try:
        result = discover_jobs()
        DISCOVERY_STATE.update({'running': False, 'result': result, 'error': None})
    except Exception as exc:
        app.logger.exception('Dashboard discovery failed')
        DISCOVERY_STATE.update({'running': False, 'result': None, 'error': f'{type(exc).__name__}: {exc}'})

@app.post('/admin/ui/run')
@require_basic_auth
def ui_run():
    with DISCOVERY_LOCK:
        if DISCOVERY_STATE['running']:
            return jsonify({'ok': True, 'running': True}), 202
        DISCOVERY_STATE.update({'running': True, 'result': None, 'error': None})
        threading.Thread(target=_background_discovery, daemon=True).start()
    return jsonify({'ok': True, 'running': True, 'message': 'Discovery started'}), 202

@app.get('/admin/ui/run-status')
@require_basic_auth
def ui_run_status():
    return jsonify({'ok': True, **DISCOVERY_STATE})

@app.post('/admin/ui/approve/<int:job_id>')
@require_basic_auth
def ui_approve(job_id):
    changed = approve_job(job_id)
    return jsonify({'ok': changed}), (200 if changed else 404)

@app.post('/admin/ui/publish')
@require_basic_auth
def ui_publish():
    sent, failed = [], []
    for job in get_jobs(status='approved', limit=100):
        try:
            send_job(job)
            mark_posted(job['id'])
            sent.append(job['id'])
        except Exception as exc:
            app.logger.exception('Dashboard Telegram publish failed for job %s', job['id'])
            failed.append({'id': job['id'], 'error': str(exc)})
    return jsonify({'ok': not failed, 'published_ids': sent, 'failed': failed})

@app.get('/')
def home(): return jsonify({'service':'TechTis Sarkari Naukari Automation','status':'running','scheduler':'External cron-job.org','discovery_interval':'3 hours','publishing':'Manual approval required'})
@app.get('/health')
def health(): return jsonify({'ok':True,'service':'techtis-job-automation'})
@app.get('/db-health')
def public_db_health():
    try:
        from db import connection, execute
        with connection() as conn:
            execute(conn, 'SELECT 1').fetchone()
        return jsonify({'ok': True, 'database': 'connected'})
    except Exception:
        app.logger.exception('Public database health check failed')
        return jsonify({'ok': False, 'database': 'connection_failed'}), 500

@app.get('/admin/db-check')
@require_secret
def db_check():
    try:
        from db import connection, execute
        with connection() as conn:
            row = execute(conn, 'SELECT COUNT(*) AS total FROM jobs').fetchone()
            total = row['total'] if hasattr(row, '__getitem__') else row[0]
        return jsonify({'ok': True, 'database': 'connected', 'jobs_table': 'available', 'total_jobs': total})
    except Exception as exc:
        app.logger.exception('Database check failed')
        return jsonify({'ok': False, 'error': str(exc)}), 500

@app.get('/admin/telegram-chat-info')
@require_secret
def telegram_chat_info():
    import requests
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        return jsonify({'ok': False, 'error': 'Telegram bot token is missing'}), 400
    try:
        response = requests.get(f'https://api.telegram.org/bot{token}/getUpdates', timeout=20)
        data = response.json()
        if not data.get('ok'):
            return jsonify({'ok': False, 'error': data.get('description', 'Telegram API error')}), 502
        chats = []
        for update in data.get('result', []):
            post = update.get('channel_post') or update.get('edited_channel_post')
            if post and post.get('chat'):
                chat = post['chat']
                item = {'id': chat.get('id'), 'title': chat.get('title'), 'username': chat.get('username')}
                if item not in chats:
                    chats.append(item)
        return jsonify({'ok': True, 'channels_found': chats, 'hint': 'If empty, check whether the bot is an admin and send a fresh channel post, then retry.'})
    except Exception as exc:
        app.logger.exception('Telegram chat lookup failed')
        return jsonify({'ok': False, 'error': f'Telegram lookup failed ({type(exc).__name__})'}), 502

@app.post('/admin/test-telegram')
@require_secret
def test_telegram():
    try:
        send_job({'title': 'Test message: TechTis Sarkari Naukari bot is connected', 'source': 'TechTis setup test', 'published': '', 'summary': '', 'url': 'https://techtis.in'})
        return jsonify({'ok': True, 'message': 'Telegram test message sent'})
    except Exception as exc:
        app.logger.exception('Telegram test failed')
        return jsonify({'ok': False, 'error': str(exc)}), 500

@app.post('/run')
@require_secret
def run_discovery():
    try: return jsonify({'ok':True,'discovery':discover_jobs()})
    except Exception as exc:
        app.logger.exception('Discovery failed'); return jsonify({'ok':False,'error':str(exc)}),500
@app.get('/admin/jobs')
@require_secret
def admin_jobs(): return jsonify({'ok':True,'jobs':get_jobs(status=request.args.get('status'))})
@app.post('/admin/approve/<int:job_id>')
@require_secret
def admin_approve(job_id):
    changed=approve_job(job_id); return jsonify({'ok':changed,'message':'Approved' if changed else 'No pending job with that ID'}),(200 if changed else 404)
@app.post('/admin/publish')
@require_secret
def admin_publish():
    sent=[]; failed=[]
    for job in get_jobs(status='approved',limit=100):
        try: send_job(job); mark_posted(job['id']); sent.append(job['id'])
        except Exception as exc:
            app.logger.exception('Telegram publish failed for job %s',job['id']); failed.append({'id':job['id'],'error':str(exc)})
    return jsonify({'ok':not failed,'published_ids':sent,'failed':failed})
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))
