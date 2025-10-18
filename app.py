import os
import requests
import base64
import re
import chainlit as cl
from dotenv import load_dotenv
import google.generativeai as genai
import asyncio
import sys

# Fix for Windows asyncio event loop
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ----------------- Load environment variables -----------------
load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ----------------- Configure Gemini -----------------
genai.configure(api_key=GEMINI_API_KEY)

# ----------------- GitHub headers -----------------
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# ----------------- GitHub Functions -----------------
def create_repo(repo_name, private=True):
    url = "https://api.github.com/user/repos"
    data = {"name": repo_name, "private": private}
    response = requests.post(url, headers=HEADERS, json=data)
    return response.json()

def list_repos():
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        repos = response.json()
        if not repos:
            return ["⚠️ No repositories found!"]
        return [repo["name"] for repo in repos]
    else:
        return [f"Error {response.status_code}: {response.text}"]

def delete_repo(repo_name):
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}"
    response = requests.delete(url, headers=HEADERS)
    return response.status_code == 204

def add_or_update_file(repo_name, file_path, content, commit_msg="Add/Update file"):
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/{file_path}"
    r = requests.get(url, headers=HEADERS)
    sha = r.json().get("sha") if r.status_code == 200 else None

    data = {
        "message": commit_msg,
        "content": base64.b64encode(content.encode()).decode()
    }
    if sha:
        data["sha"] = sha

    response = requests.put(url, headers=HEADERS, json=data)
    if response.status_code in [200, 201]:
        return response.json()
    else:
        raise Exception(f"GitHub API error: {response.status_code}, {response.text}")

# ----------------- Gemini AI -----------------
def ask_gemini(prompt):
    response = genai.GenerativeModel("gemini-2.5-flash").generate_content(prompt)
    return response.text

async def ask_gemini_async(prompt):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: ask_gemini(prompt))

# ----------------- Chainlit App -----------------
@cl.on_chat_start
async def start():
    await cl.Message(content="# 🤖 Personal Github Agent\nAsk me to create, delete, list repos, or manage files!\nYou can also ask me anything with Gemini AI.").send()

@cl.on_message
async def main(message: cl.Message):
    user_input = message.content.strip()
    response_text = "❓ Sorry, I didn't understand that command!"

    # ----------------- Repo Commands -----------------
    if match := re.match(r'create repo named "?(.+?)"?$', user_input, re.IGNORECASE):
        repo_name = match.group(1).strip()
        result = create_repo(repo_name)
        response_text = f"✅ Repo '{repo_name}' created!\nURL: {result.get('html_url', 'N/A')}"

    elif re.match(r'list( of)?( my)? repos', user_input, re.IGNORECASE):
        repos = list_repos()
        response_text = "📂 Your Repos:\n" + "\n".join(repos)

    elif match := re.match(r'delete repo named "?(.+?)"?$', user_input, re.IGNORECASE):
        repo_name = match.group(1).strip()
        success = delete_repo(repo_name)
        response_text = f"🗑️ Repo '{repo_name}' deleted!" if success else f"⚠️ Failed to delete '{repo_name}'."

    elif match := re.match(
        r'(?:add|create|update) file\s+(.+?)\s+(?:in|to)\s+repo\s+"?([^"]+)"?\s+with content\s+(.+)',
        user_input,
        re.IGNORECASE
    ):
        file_path = match.group(1).strip()
        repo_name = match.group(2).strip()
        content = match.group(3).strip()
        try:
            result = add_or_update_file(repo_name, file_path, content)
            file_url = result.get("content", {}).get("html_url", "N/A")
            response_text = f"📄 File '{file_path}' created/updated in repo '{repo_name}'!\nURL: {file_url}"
        except Exception as e:
            response_text = f"⚠️ Could not add/update file: {e}"

    # ----------------- Fallback to Gemini AI -----------------
    else:
        response_text = await ask_gemini_async(user_input)

    # 🔹 Send response back to Chainlit
    await cl.Message(content=response_text).send()
