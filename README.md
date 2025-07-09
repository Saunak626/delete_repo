# delete_repo
网页端批量删除github仓库

1. 在[github](https://github.com/settings/tokens)创建token，选择delete权限
2. 环境配置
```python
pip install streamlit pandas requests
```
3. 运行
```python
streamlit run app.py
```
运行后点击终端中的 http链接即可进行操作。
输入token