#!/usr/bin/env python3
"""
GitHub API部署脚本 - valuation workspace
使用GitHub API上传Streamlit应用文件到GitHub，触发Streamlit Cloud自动部署
"""
import os
import base64
import requests
from pathlib import Path

# 配置
REPO_OWNER = "skywalkern-cloud"
REPO_NAME = "alibaba-valuation"
BRANCH = "main"
GH_TOKEN = os.environ.get('GH_TOKEN', '') or os.environ.get('GITHUB_TOKEN', '')
if not GH_TOKEN:
    token_file = Path(__file__).parent.parent / '.gh_token'
    if token_file.exists():
        GH_TOKEN = token_file.read_text().strip()
if not GH_TOKEN:
    # Token should be provided via GH_TOKEN env var or ~/.openclaw/.gh_token file
    raise ValueError('GitHub token not found. Set GH_TOKEN env var or create ~/.openclaw/.gh_token')

WORK_DIR = Path("~/.openclaw/workspace-alibaba").expanduser()

# 上传哪些文件/目录
UPLOAD_PATHS = [
    "app.py",
    "requirements.txt",
    ".streamlit/config.toml",
    "common/",
    "stocks/",
    "scripts/",
    "data/",
]

SKIP_FILES = ["deploy_via_api.py", ".DS_Store", "__pycache__", "*.pyc"]


def get_file_sha(repo_path):
    """获取文件SHA用于更新"""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{repo_path}"
    headers = {"Authorization": f"token {GH_TOKEN}"}
    params = {"ref": BRANCH}
    r = requests.get(url, headers=headers, params=params)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def should_skip(path):
    """检查是否跳过"""
    name = path.name
    for pattern in SKIP_FILES:
        if pattern.startswith("*") and name.endswith(pattern[1:]):
            return True
        if name == pattern:
            return True
    return False


def upload_file(file_path, repo_path):
    """上传单个文件"""
    if should_skip(file_path):
        print(f"  ⏭️ 跳过: {repo_path}")
        return True

    try:
        with open(file_path, "rb") as f:
            content = f.read()
    except Exception as e:
        print(f"  ❌ 读取失败: {repo_path} - {e}")
        return False

    b64_content = base64.b64encode(content).decode("utf-8")

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{repo_path}"
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "message": f"Deploy update: {file_path.name}",
        "content": b64_content,
        "branch": BRANCH
    }

    sha = get_file_sha(repo_path)
    if sha:
        data["sha"] = sha

    r = requests.put(url, headers=headers, json=data)
    if r.status_code in [200, 201]:
        print(f"  ✅ {repo_path}")
        return True
    else:
        print(f"  ❌ {repo_path}: {r.status_code} - {r.text[:200]}")
        return False


def collect_files():
    """收集所有需要上传的文件"""
    files = []
    for upload_path in UPLOAD_PATHS:
        full_path = WORK_DIR / upload_path
        if full_path.is_file():
            files.append((full_path, upload_path))
        elif full_path.is_dir():
            for root, dirs, filenames in os.walk(full_path):
                for f in filenames:
                    fp = Path(root) / f
                    rel = fp.relative_to(WORK_DIR)
                    files.append((fp, str(rel)))
    return files


def main():
    from datetime import datetime
    print("=" * 60)
    print("Valuation GitHub API 部署")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"仓库: {REPO_OWNER}/{REPO_NAME}")
    print("=" * 60)

    files = collect_files()
    print(f"\n待上传: {len(files)} 个文件/目录")

    success = 0
    failed = 0

    for full_path, repo_path in files:
        if upload_file(full_path, repo_path):
            success += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    if failed == 0:
        print(f"✅ 部署完成! 成功: {success}")
        print(f"🌐 Streamlit Cloud会自动更新 (需要已连接仓库)")
    else:
        print(f"⚠️ 部分失败: 成功 {success}, 失败 {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()