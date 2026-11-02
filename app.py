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
