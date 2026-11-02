import argparse
from dotenv import load_dotenv
load_dotenv()

from job_engine import discover_jobs, get_jobs, approve_job, mark_posted
from telegram import send_job

parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="cmd", required=True)
sub.add_parser("discover")
sub.add_parser("list")
approve = sub.add_parser("approve")
approve.add_argument("id", type=int)
sub.add_parser("publish")
args = parser.parse_args()

if args.cmd == "discover":
    print(discover_jobs())
elif args.cmd == "list":
    for job in get_jobs():
        print(f"[{job['id']}] {job['status'].upper()} | {job['source']} | {job['title']}\n{job['url']}\n")
elif args.cmd == "approve":
    print("Approved" if approve_job(args.id) else "No pending job found.")
elif args.cmd == "publish":
    for job in get_jobs(status="approved"):
        try:
            send_job(job)
            mark_posted(job["id"])
            print(f"Published {job['id']}")
        except Exception as exc:
            print(f"Failed {job['id']}: {exc}")
