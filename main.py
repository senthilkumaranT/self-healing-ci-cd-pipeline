import os
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("webhook_server.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("webhook_handler")

app = FastAPI(title="Self-Healing CI/CD Webhook Receiver")

class WebhookPayload(BaseModel):
    repository: str  # e.g., "owner/repo"
    run_id: str      # e.g., "123456789"
    token: Optional[str] = None

def fetch_and_log_github_failure(repository: str, run_id: str, token: Optional[str]):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    # Use provided token or environment token
    github_token = token or os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
        logger.info("Using authorization token for GitHub API request.")
    else:
        logger.warning("No GitHub token provided. API requests might be rate-limited or fail for private repositories.")

    jobs_url = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs"
    
    try:
        with httpx.Client(follow_redirects=True) as client:
            logger.info(f"Fetching jobs from URL: {jobs_url}")
            response = client.get(jobs_url, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch jobs: HTTP {response.status_code} - {response.text}")
                return
                
            jobs_data = response.json()
            jobs = jobs_data.get("jobs", [])
            logger.info(f"Found {len(jobs)} jobs in workflow run {run_id}")
            
            failed_jobs = [j for j in jobs if j.get("conclusion") == "failure" or j.get("status") == "completed" and j.get("conclusion") in ["failure", "cancelled"]]
            
            # Fallback to all jobs if no failed jobs are found, so triggering always prints logs
            jobs_to_log = failed_jobs if failed_jobs else jobs
            
            if not jobs_to_log:
                logger.info("No jobs found in the workflow run.")
                return
                
            for job in jobs_to_log:
                job_id = job.get("id")
                job_name = job.get("name")
                logger.info(f"Processing failed job: {job_name} (ID: {job_id})")
                
                logs_url = f"https://api.github.com/repos/{repository}/actions/jobs/{job_id}/logs"
                logger.info(f"Fetching logs from: {logs_url}")
                
                logs_response = client.get(logs_url, headers=headers)
                if logs_response.status_code != 200:
                    logger.error(f"Failed to fetch logs for job {job_id}: HTTP {logs_response.status_code}")
                    continue
                    
                log_text = logs_response.text
                
                # Print/Log the response logs
                logger.info(f"=== START OF LOGS FOR JOB: {job_name} ===")
                # Print to stdout/file
                print(log_text)
                logger.info(f"=== END OF LOGS FOR JOB: {job_name} ===")
                
                # Save the log to a file for analysis
                log_filename = f"failed_job_{job_id}.log"
                with open(log_filename, "w", encoding="utf-8") as f:
                    f.write(log_text)
                logger.info(f"Saved failed job logs to {log_filename}")
                
    except Exception as e:
        logger.exception(f"Error occurred during fetching GitHub Action response: {e}")

@app.post("/webhook")
async def receive_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    logger.info(f"Received webhook trigger for repository: {payload.repository}, Run ID: {payload.run_id}")
    
    # Process the job logs asynchronously in the background so the webhook response is fast
    background_tasks.add_task(
        fetch_and_log_github_failure,
        payload.repository,
        payload.run_id,
        payload.token
    )
    
    return {
        "status": "success",
        "message": f"Webhook received. Processing run {payload.run_id} in the background."
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}
