from flask import Flask, render_template, request, jsonify, session
import requests
from datetime import datetime, timezone
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

DEFAULT_DAYS_STALE = 365


def fetch_repos(token):
    """获取所有仓库"""
    headers = {'Authorization': f'token {token}',
               'Accept': 'application/vnd.github.v3+json'}
    repos, page = [], 1

    while True:
        url = (f"https://api.github.com/user/repos?per_page=100&page={page}"
               f"&sort=updated&direction=desc")
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            return None, str(e)

        data = r.json()
        if not data:
            break
        repos.extend(data)
        page += 1

    return repos, None


def analyze_repo(repo):
    """分析单个仓库"""
    now = datetime.now(timezone.utc)
    created = datetime.fromisoformat(repo['created_at'].replace('Z', '+00:00'))
    last_activity = datetime.fromisoformat(
        repo['updated_at'].replace('Z', '+00:00'))

    days_inactive = (now - last_activity).days
    is_fork = repo['fork']
    stars = repo['stargazers_count']
    is_archived = repo['archived']

    # 风险评估分数（0-4）
    score = (
        int(is_fork) +
        int(stars == 0) +
        int(days_inactive > DEFAULT_DAYS_STALE) +
        int(is_fork and (last_activity - created).total_seconds() < 120)
    )

    notes = []
    if days_inactive > DEFAULT_DAYS_STALE:
        notes.append(f"长期未活动({days_inactive}天)")
    if is_fork and (last_activity - created).total_seconds() < 120:
        notes.append("Fork后未活动")
    if is_archived:
        notes.append("已归档")

    return {
        "full_name": repo["full_name"],
        "repo_url": repo["html_url"],
        "last_activity_at": repo["updated_at"][:10],
        "private": repo["private"],
        "fork": is_fork,
        "archived": is_archived,
        "stars": stars,
        "days_inactive": days_inactive,
        "note": ", ".join(notes),
        "suggestion_score": score,
        "lock_repo": False,
        "archive_selected": False,
        "delete_selected": False
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/fetch_repos', methods=['POST'])
def api_fetch_repos():
    """API: 获取仓库列表"""
    data = request.json
    token = data.get('token')

    if not token:
        return jsonify({'error': '请提供 GitHub Token'}), 400

    repos, error = fetch_repos(token)
    if error:
        return jsonify({'error': f'获取仓库失败: {error}'}), 400

    if not repos:
        return jsonify({'repos': []})

    analyzed_repos = [analyze_repo(repo) for repo in repos]
    session['repos'] = analyzed_repos
    session['token'] = token

    return jsonify({'repos': analyzed_repos})


@app.route('/api/update_selections', methods=['POST'])
def api_update_selections():
    """API: 更新选择状态"""
    data = request.json
    selections = data.get('selections', {})

    if 'repos' not in session:
        return jsonify({'error': '请先获取仓库列表'}), 400

    # 更新选择状态
    for repo in session['repos']:
        repo_name = repo['full_name']
        if repo_name in selections:
            repo.update(selections[repo_name])

    return jsonify({'success': True})


@app.route('/api/execute_archive', methods=['POST'])
def api_execute_archive():
    """API: 执行归档操作"""
    if 'repos' not in session or 'token' not in session:
        return jsonify({'error': '会话已过期'}), 400

    headers = {'Authorization': f'token {session["token"]}',
               'Accept': 'application/vnd.github.v3+json'}

    to_archive = [repo for repo in session['repos']
                  if repo.get('archive_selected', False)]

    if not to_archive:
        return jsonify({'error': '没有选中要归档的仓库'}), 400

    success_count = 0
    errors = []

    for repo in to_archive:
        try:
            r = requests.patch(
                f"https://api.github.com/repos/{repo['full_name']}",
                headers=headers,
                json={"archived": True}
            )
            r.raise_for_status()
            success_count += 1
            # 更新本地状态
            repo['archive_selected'] = False
            repo['archived'] = True
        except Exception as e:
            errors.append(f"{repo['full_name']}: {str(e)}")

    return jsonify({
        'success': True,
        'archived_count': success_count,
        'errors': errors
    })


@app.route('/api/execute_delete', methods=['POST'])
def api_execute_delete():
    """API: 执行删除操作"""
    data = request.json
    repos_to_delete_names = data.get('repos_to_delete', [])

    if not repos_to_delete_names:
        return jsonify({'error': '没有选中要删除的仓库'}), 400

    if 'repos' not in session or 'token' not in session:
        return jsonify({'error': '会话已过期'}), 400

    headers = {'Authorization': f'token {session["token"]}',
               'Accept': 'application/vnd.github.v3+json'}

    # 从会话中根据名称过滤出要操作的仓库
    all_repos_map = {repo['full_name']: repo for repo in session['repos']}
    to_delete = [all_repos_map[name] for name in repos_to_delete_names
                 if name in all_repos_map]

    # 检查锁定状态
    locked_repos = [repo for repo in to_delete
                    if repo.get('lock_repo', False)]

    if locked_repos:
        locked_names = [repo['full_name'] for repo in locked_repos]
        return jsonify({
            'error': '以下仓库被锁定，无法删除',
            'locked_repos': locked_names
        }), 400

    if not to_delete:
        return jsonify({'error': '没有选中要删除的仓库'}), 400

    success_count = 0
    errors = []

    for repo in to_delete:
        try:
            r = requests.delete(
                f"https://api.github.com/repos/{repo['full_name']}",
                headers=headers
            )
            r.raise_for_status()
            success_count += 1
        except Exception as e:
            errors.append(f"{repo['full_name']}: {str(e)}")

    # 从会话中移除已删除的仓库
    error_repos = [err.split(':')[0] for err in errors]
    session['repos'] = [repo for repo in session['repos']
                        if repo['full_name'] not in repos_to_delete_names or
                        repo['full_name'] in error_repos]

    return jsonify({
        'success': True,
        'deleted_count': success_count,
        'errors': errors
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
