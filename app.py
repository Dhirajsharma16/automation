import hmac, os
from functools import wraps
from flask import Flask, jsonify, request
from dotenv import load_dotenv
load_dotenv()
from job_engine import discover_jobs, get_jobs, approve_job, mark_posted
from telegram import send_job
app=Flask(__name__); SECRET=os.getenv('AUTOMATION_SECRET','')

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
        auth = request.authorization
        supplied = auth.password if auth and auth.username == 'admin' else ''
        if not SECRET or not supplied or not hmac.compare_digest(supplied, SECRET):
            response = jsonify({'ok': False, 'error': 'Login required'})
            response.status_code = 401
            response.headers['WWW-Authenticate'] = 'Basic realm="TechTis Admin", charset="UTF-8"'
            return response
        return fn(*args, **kwargs)
    return wrapper

DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TechTis | Sarkari Naukari Admin</title>
<style>
body{font-family:Arial,sans-serif;background:#f5f7fb;color:#172033;margin:0;padding:24px}
main{max-width:950px;margin:auto}.card{background:white;border:1px solid #e3e8f0;border-radius:12px;padding:18px;margin:14px 0}
h1{font-size:25px}.muted{color:#667085}.actions{display:flex;gap:10px;flex-wrap:wrap}
button{border:0;border-radius:8px;padding:11px 15px;background:#175cd3;color:white;cursor:pointer}
button.secondary{background:#475467}button:disabled{opacity:.5;cursor:wait}
.job{border-top:1px solid #eaecf0;padding:14px 0}.job a{color:#175cd3;overflow-wrap:anywhere}
.status{font-size:13px;color:#667085}pre{white-space:pre-wrap;overflow-wrap:anywhere}
</style></head><body><main>
<h1>TechTis Sarkari Naukari</h1><p class="muted">Private admin dashboard. Jobs stay pending until you approve them.</p>
<section class="card"><div class="actions">
<button onclick="runSearch()">Search for new jobs</button>
<button class="secondary" onclick="loadJobs()">Refresh jobs</button>
<button class="secondary" onclick="publishApproved()">Publish approved jobs</button>
</div><p id="message" class="status">Ready.</p></section>
<section class="card"><h2>Pending jobs</h2><div id="pending">Loading…</div></section>
<section class="card"><h2>Approved jobs</h2><div id="approved">Loading…</div></section>
<section class="card"><h2>Recently posted</h2><div id="posted">Loading…</div></section>
</main>
<script>
const msg=document.getElementById('message');
async function api(path,method='GET'){const r=await fetch(path,{method,credentials:'same-origin'});const data=await r.json().catch(()=>({error:'Unexpected server response'}));if(!r.ok)throw new Error(data.error||('HTTP '+r.status));return data;}
function say(t){msg.textContent=t;}
async function runSearch(){say('Searching official feeds…');try{const d=await api('/admin/ui/run','POST');say('Search complete. Sources checked: '+d.discovery.sources_checked+', new jobs: '+d.discovery.new_items+(d.discovery.errors.length?' | Errors: '+d.discovery.errors.join('; '):''));await loadJobs();}catch(e){say(e.message);}}
async function approve(id){say('Approving job…');try{await api('/admin/ui/approve/'+id,'POST');say('Job approved.');await loadJobs();}catch(e){say(e.message);}}
async function publishApproved(){if(!confirm('Publish all approved jobs to Telegram?'))return;say('Publishing approved jobs…');try{const d=await api('/admin/ui/publish','POST');say('Published: '+d.published_ids.length+(d.failed.length?' | Failed: '+d.failed.length:''));await loadJobs();}catch(e){say(e.message);}}
function renderList(target,items,canApprove){const el=document.getElementById(target);el.replaceChildren();if(!items.length){el.textContent='No jobs here yet.';return;}for(const j of items){const div=document.createElement('div');div.className='job';const title=document.createElement('strong');title.textContent=j.title;const meta=document.createElement('p');meta.className='status';meta.textContent=(j.source||'')+' · '+(j.published||'Date not listed')+' · '+j.status;const link=document.createElement('a');link.href=j.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Open official notice';div.append(title,meta,link);if(j.summary){const p=document.createElement('p');p.textContent=j.summary;div.append(p);}if(canApprove){const b=document.createElement('button');b.textContent='Approve';b.onclick=()=>approve(j.id);div.append(b);}el.append(div);}}
async function loadJobs(){try{const d=await api('/admin/ui/jobs');const jobs=d.jobs;renderList('pending',jobs.filter(x=>x.status==='pending'),true);renderList('approved',jobs.filter(x=>x.status==='approved'),false);renderList('posted',jobs.filter(x=>x.status==='posted'),false);}catch(e){say(e.message);}}
loadJobs();
</script></body></html>"""

@app.get('/dashboard')
@require_basic_auth
def dashboard():
    return DASHBOARD_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.get('/admin/ui/jobs')
@require_basic_auth
def ui_jobs():
    return jsonify({'ok': True, 'jobs': get_jobs(limit=200)})

@app.post('/admin/ui/run')
@require_basic_auth
def ui_run():
    try:
        return jsonify({'ok': True, 'discovery': discover_jobs()})
    except Exception as exc:
        app.logger.exception('Dashboard discovery failed')
        return jsonify({'ok': False, 'error': str(exc)}), 500

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
