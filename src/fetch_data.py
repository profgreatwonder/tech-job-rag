import json
import urllib.request
import os

def fetch_sample_jobs():
    print("Fetching live tech job dataset from public Remote Jobs API...")
    url = "https://jobicy.com/api/v2/remote-jobs?count=50&industry=engineering"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            payload = json.loads(response.read().decode())
            jobs_raw = payload.get("jobs", [])
            
        sample_jobs = []
        for item in jobs_raw:
            sample_jobs.append({
                "job_id": str(item.get("id", "")),
                "title": item.get("jobTitle", "Tech Role"),
                "company": item.get("companyName", "Unknown Company"),
                "location": item.get("jobGeo", "Remote"),
                "schedule_type": ", ".join(item.get("jobType", ["Full-time"])) if isinstance(item.get("jobType"), list) else str(item.get("jobType", "Full-time")),
                "description": (item.get("jobExcerpt", "") or "") + " " + (item.get("jobDescription", "") or ""),
                "skills": ", ".join(item.get("jobIndustry", ["Technology"])) if isinstance(item.get("jobIndustry"), list) else str(item.get("jobIndustry", "Technology"))
            })

        os.makedirs("data", exist_ok=True)
        with open("data/raw_jobs.json", "w", encoding="utf-8") as f:
            json.dump(sample_jobs, f, indent=2)
            
        print(f"Successfully saved {len(sample_jobs)} tech job postings to data/raw_jobs.json")

    except Exception as e:
        print(f"Error fetching dataset: {e}")

if __name__ == "__main__":
    fetch_sample_jobs()