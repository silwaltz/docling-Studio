import json, time, urllib.request, sys

JOB_ID = "b3d7bfa4-ce64-4cf6-9879-54a00f465145"

for i in range(40):
    time.sleep(15)
    try:
        r = urllib.request.urlopen(f"http://localhost:8000/api/analyses/{JOB_ID}").read()
        d = json.loads(r)
        status = d.get("status")
        pc = d.get("progressCurrent")
        pt = d.get("progressTotal")
        em = (d.get("errorMessage") or "")[:80]
        print(f"  [{i*15:>3d}s] {status} {pc}/{pt} {em}", flush=True)
        if status in ("COMPLETED", "FAILED"):
            if status == "COMPLETED":
                cj = d.get("contentJson")
                if cj:
                    parsed = json.loads(cj) if isinstance(cj, str) else cj
                    merged = parsed[0] if isinstance(parsed, list) and parsed else parsed
                    if isinstance(merged, dict):
                        print("merged keys:", len(merged))
                        for k, v in list(merged.items()):
                            print(f"  {k}: {v[:140]}")
            sys.exit(0)
    except Exception as e:
        print(f"  [{i*15:>3d}s] error: {e}", flush=True)
