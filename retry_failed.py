import os
import sys
import time
import requests

API = "https://async.api.zenrows.com/v1"
HEADERS = {"X-API-Key": os.environ["ZENROWS_API_KEY"]}
job_id = sys.argv[1]

r = requests.post(f"{API}/jobs/{job_id}/rerun", headers=HEADERS,
                  params={"status": "failed"}, timeout=60)
print(r.status_code, r.json())

while True:
    run = requests.get(f"{API}/jobs/{job_id}", headers=HEADERS, timeout=60).json()["latest_run"]
    if run["status"] in ("completed", "failed", "stopped"):
        break
    time.sleep(15)
print(f'run {run["run_sequence"]}: {run["stats"]}')

page = requests.get(f"{API}/jobs/{job_id}/results", headers=HEADERS,
                    params={"status": "all"}, timeout=60).json()
for row in page["results"]:
    print(f'{row["external_id"]:<40} {row["status"]}')
