import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone

# -------------------- 基本配置 --------------------
st.set_page_config(page_title="GitHub 仓库批量管理助手", layout="wide")
DEFAULT_DAYS_STALE = 365

st.title("📦 GitHub 仓库批量管理工具")
st.markdown(
    "勾选以锁定、归档或删除仓库。"
    "**归档**将仓库设为只读；**锁定**后无法删除。"
)

# -------------------- 输入 Token --------------------
token = st.text_input(
    "请输入 GitHub Personal Access Token（需 repo & delete_repo 权限）",
    type="password"
)

# -------------------- 函数：获取仓库 --------------------


@st.cache_data(show_spinner="正在获取仓库列表...")
def fetch_repos(_headers):
    repos, page = [], 1
    while True:
        url = (f"https://api.github.com/user/repos?per_page=100&page={page}"
               f"&sort=updated&direction=desc")
        try:
            r = requests.get(url, headers=_headers, timeout=10)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            st.error(f"获取仓库失败: {e}")
            return None
        data = r.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

# -------------------- 函数：分析仓库 --------------------


def analyze_repo(repo):
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
        "lock_repo": False,
        "archive_selected": False,
        "delete_selected": False,
        "full_name": repo["full_name"],
        "repo_url":  repo["html_url"],
        "last_activity_at": repo["updated_at"][:10],
        "private":   repo["private"],
        "fork":      is_fork,
        "archived":  is_archived,
        "stars":     stars,
        "days_inactive": days_inactive,
        "note": ", ".join(notes),
        "suggestion_score": score,
    }


# -------------------- 主逻辑 --------------------
if token:
    headers = {'Authorization': f'token {token}',
               'Accept': 'application/vnd.github.v3+json'}
    raw = fetch_repos(headers)

    if raw:
        # 初始化或刷新 session_state.repo_df
        if ("repo_df" not in st.session_state or
                not isinstance(st.session_state.repo_df, pd.DataFrame)):
            st.session_state.repo_df = pd.DataFrame(
                [analyze_repo(r) for r in raw])
        else:
            # 保留用户勾选状态，仅更新数据
            df_new = pd.DataFrame([analyze_repo(r) for r in raw])
            cols_to_preserve = [
                "full_name", "lock_repo",
                "archive_selected", "delete_selected"
            ]
            current_selection = st.session_state.repo_df[cols_to_preserve]
            cols_to_drop = [
                c for c in cols_to_preserve if c != "full_name"]

            df_new = df_new.drop(columns=cols_to_drop, errors='ignore')
            df_new = pd.merge(df_new, current_selection,
                              on="full_name", how="left")
            for col in cols_to_drop:
                df_new[col] = df_new[col].fillna(False)
            st.session_state.repo_df = df_new

        # ---------- 筛选和批量操作 ----------
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            threshold = st.slider(
                "筛选：风险分数 ≥", 0, 4, 0, key="filter_slider")

        # 根据筛选阈值生成可视数据集
        show_df = st.session_state.repo_df.copy()
        if threshold > 0:
            show_df = show_df[show_df["suggestion_score"] >= threshold]
            st.info(
                f"筛选显示：风险分数 ≥ {threshold} 的仓库（共 {len(show_df)} 个）")
        visible_idx = show_df.index

        with col2:
            if st.button("✅ 全选删除"):
                st.session_state.repo_df.loc[visible_idx,
                                             "delete_selected"] = True
                st.rerun()
        with col3:
            if st.button("🔄 重置选择"):
                st.session_state.repo_df.loc[
                    visible_idx,
                    ["archive_selected", "delete_selected"]
                ] = False
                st.rerun()
        with col4:
            if st.button("⚙️ 按分数选中删除"):
                mask = show_df["suggestion_score"] >= threshold
                st.session_state.repo_df.loc[
                    visible_idx[mask], "delete_selected"] = True
                st.rerun()

        # ---------- Data Editor ----------
        st.markdown("**💡 使用说明：** 只有`锁定`、`归档`、`删除`三列可以编辑。")

        show_df_display = show_df.copy()
        show_df_display["repo_link"] = show_df_display["repo_url"]

        edited = st.data_editor(
            show_df_display[[
                "lock_repo", "archive_selected", "delete_selected",
                "full_name", "repo_link", "suggestion_score",
                "private", "fork", "archived", "stars", "last_activity_at",
                "days_inactive", "note"
            ]],
            column_config={
                "lock_repo": st.column_config.CheckboxColumn(
                    "🔒 锁定", help="勾选后无法删除", width="small"),
                "archive_selected": st.column_config.CheckboxColumn(
                    "📦 归档", help="将仓库设为只读", width="small"),
                "delete_selected": st.column_config.CheckboxColumn(
                    "🗑️ 删除", help="勾选以删除仓库", width="small"),
                "full_name": st.column_config.TextColumn(
                    "仓库名", disabled=True),
                "repo_link": st.column_config.LinkColumn(
                    "链接", help="点击访问仓库", display_text="访问",
                    disabled=True, width="small"),
                "suggestion_score": st.column_config.NumberColumn(
                    "风险分数", disabled=True, width="small"),
                "private": st.column_config.CheckboxColumn(
                    "私有", disabled=True, width="small"),
                "fork": st.column_config.CheckboxColumn(
                    "Fork", disabled=True, width="small"),
                "archived": st.column_config.CheckboxColumn(
                    "已归档", disabled=True, width="small"),
                "stars": st.column_config.NumberColumn(
                    "Stars", disabled=True, width="small"),
                "last_activity_at": st.column_config.TextColumn(
                    "最近活动", disabled=True, width="small"),
                "days_inactive": st.column_config.NumberColumn(
                    "未活动(天)", disabled=True, width="small"),
                "note": st.column_config.TextColumn(
                    "备注", disabled=True, width="medium")
            },
            use_container_width=True,
            hide_index=True,
            height=600,
            key="editor")

        changes = edited[[
            "full_name", "lock_repo", "archive_selected", "delete_selected"]]
        current_df = st.session_state.repo_df.set_index("full_name")
        changes = changes.set_index("full_name")
        current_df.update(changes)
        st.session_state.repo_df = current_df.reset_index()

        # ---------- 执行操作 ----------
        to_archive = st.session_state.repo_df.query("archive_selected == True")
        to_delete = st.session_state.repo_df.query("delete_selected == True")

        if not to_archive.empty or not to_delete.empty:
            st.markdown("---")
            col_archive, col_delete = st.columns(2)

            with col_archive:
                if not to_archive.empty:
                    st.info(f"**{len(to_archive)}** 个仓库待归档")
                    if st.button("📦 执行归档"):
                        with st.spinner("归档中..."):
                            for repo in to_archive["full_name"]:
                                requests.patch(
                                    f"https://api.github.com/repos/{repo}",
                                    headers=headers, json={"archived": True})
                        st.success(f"已归档 {len(to_archive)} 个仓库")
                        st.session_state.repo_df = None
                        st.cache_data.clear()
                        st.rerun()

            with col_delete:
                if not to_delete.empty:
                    st.warning(f"**{len(to_delete)}** 个仓库待删除")
                    if st.button("🗑️ 执行删除", type="primary"):
                        st.session_state.show_confirm = True
                        st.rerun()

        # 删除确认框
        if st.session_state.get("show_confirm", False):
            locked_items = to_delete.query("lock_repo == True")
            if not locked_items.empty:
                st.error("以下已选仓库被锁定，无法删除，请先解锁：")
                for name in locked_items["full_name"]:
                    st.write(f"- 🔒 {name}")
                st.session_state.show_confirm = False
            else:
                st.error("⚠️ 警告：删除操作不可逆！")
                confirm_delete = st.text_input(
                    "请输入 **确认删除** 以继续：", key="delete_confirm_input")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("❌ 取消"):
                        st.session_state.show_confirm = False
                        st.rerun()
                with c2:
                    if st.button("✅ 确认删除", type="primary"):
                        if confirm_delete.strip() != "确认删除":
                            st.error("❌ 输入错误，请输入'确认删除'")
                        else:
                            with st.spinner("删除中..."):
                                for repo in to_delete["full_name"]:
                                    requests.delete(
                                        f"https://api.github.com/repos/{repo}",
                                        headers=headers)
                            st.success(f"已删除 {len(to_delete)} 个仓库")
                            st.session_state.show_confirm = False
                            st.session_state.repo_df = None
                            st.cache_data.clear()
                            st.rerun()

    elif raw is not None:
        st.info("未找到任何仓库。")
else:
    st.info("请输入有效 Token 以开始。")
