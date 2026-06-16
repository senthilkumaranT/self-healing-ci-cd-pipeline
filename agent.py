import os
import httpx
import base64
from typing import Tuple, Dict
from dotenv import load_dotenv
from google.adk.agents import Agent

# Tool 1: fetch_run_jobs
def fetch_run_jobs(repo: str, run_id: str) -> str:
    """
    Fetches the jobs for a specific GitHub Actions workflow run to identify failures.
    Returns the raw job details or error logs as a string.
    """
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token: headers["Authorization"] = f"Bearer {token}"
    
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        return f"Error fetching jobs: HTTP {response.status_code} - {response.text}"

# Tool 2: get_file_contents
def get_file_contents(repo: str, path: str) -> str:
    """
    Fetches the actual source code of a file from the repository.
    Returns the decoded file content as a string.
    """
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token: headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if "content" in data:
                return base64.b64decode(data["content"]).decode('utf-8')
            return "No content field returned."
        return f"Error fetching file: HTTP {response.status_code}"

# Tool 3: create_branch
def create_branch(repo: str, base_sha: str, new_branch_name: str) -> str:
    """
    Creates a new git branch pointing to the base_sha.
    Returns a success or failure message.
    """
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token: headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo}/git/refs"
    payload = {"ref": f"refs/heads/{new_branch_name}", "sha": base_sha}
    
    with httpx.Client() as client:
        response = client.post(url, headers=headers, json=payload)
        if response.status_code == 201 or (response.status_code == 422 and "Reference already exists" in response.text):
            return f"Successfully created branch {new_branch_name}"
        return f"Error creating branch: HTTP {response.status_code} - {response.text}"

# Tool 4: update_file
def update_file(repo: str, path: str, content: str, branch: str, sha: str) -> str:
    """
    Commits the fixed code (content) to the specified file path on the specified branch.
    You must provide the blob sha of the file being replaced.
    Returns a success or failure message.
    """
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token: headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    payload = {
        "message": "AI Auto-Fix: Resolved CI/CD Pipeline Failure",
        "content": encoded_content,
        "sha": sha,
        "branch": branch
    }
    with httpx.Client() as client:
        response = client.put(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            return "Successfully committed fix!"
        return f"Error committing file: HTTP {response.status_code} - {response.text}"

# Tool 5: get_file_sha
def get_file_sha(repo: str, path: str) -> str:
    """
    Gets the blob SHA for a specific file in the repository. This is required before calling update_file.
    """
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token: headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("sha", "")
        return ""


# Initialize the ADK Agent
cicd_agent = Agent(
    name="cicd_self_healing_agent",
    model="gemini-2.5-flash",
    instruction="""
    You are an autonomous CI/CD self-healing agent. 
    When a pipeline fails, you are given the repository name and run ID (and optionally the base_sha).
    You must automatically execute the following workflow:
    1. Call fetch_run_jobs(repo, run_id) to read the logs.
    2. Analyze the logs to identify which file caused the error and what the error is.
    3. Call get_file_contents(repo, failing_file_path) to get the broken source code.
    4. Generate a logical fix for the source code.
    5. Generate a new, descriptive branch name.
    6. Call create_branch(repo, base_sha, branch_name) to create a new branch.
    7. Call get_file_sha(repo, failing_file_path) to get the file's blob SHA.
    8. Call update_file(repo, failing_file_path, fixed_content, branch_name, file_sha) to commit the fix.
    
    Work step by step and confirm when the fix is fully committed.
    """,
    tools=[fetch_run_jobs, get_file_contents, create_branch, update_file, get_file_sha]
)

if __name__ == "__main__":
    test_repo = "senthilkumaranT/frontend_for_self_healing_cicd"
    test_run_id = "27607186455" 
    test_head_sha = "080dea81006e23606076ccf4a6f3f0293c41b87e"
    
    # Run the agent!
    prompt = f"The pipeline failed for repo {test_repo} on run {test_run_id}. The base commit SHA for branching is {test_head_sha}. Please fix the bug."
    print("Starting Autonomous Workflow...")
    response = cicd_agent(prompt)
    print("Workflow Complete!")
    print(response)
