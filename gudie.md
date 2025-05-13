# PyCharm 运行指南

## 在 PyCharm 中设置项目

### 1. 打开项目
1. 打开 PyCharm
2. 选择 `File` → `Open`
3. 选择 `hr_chatbot` 文件夹

### 2. 配置 Python 解释器
1. 点击右下角的 Python 版本
2. 选择 `Add Interpreter` → `Add Local Interpreter`
3. 选择 `Virtualenv Environment` → `New`
4. 确保 Python 版本为 3.8 或更高

### 3. 安装依赖
1. 打开 PyCharm 的终端（底部的 Terminal 标签）
2. 运行以下命令：
```bash
pip install -r requirements.txt
```

### 4. 运行项目
1. 右键点击 `app.py` 文件
2. 选择 `Run 'app'`
3. 或者使用快捷键 `Shift + F10`

### 5. 访问系统
1. 在 PyCharm 的运行窗口中会显示：
   ```
   * Running on http://127.0.0.1:5000
   ```
2. 点击该链接或在浏览器中输入 `http://localhost:5000`

## 常见问题解决

### 1. 端口被占用
如果5000端口被占用，修改 `app.py` 最后一行：
```python
app.run(debug=True, port=5001, threaded=True)  # 改为5001或其他端口
```

### 2. 依赖安装失败
使用国内镜像：
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. Azure API 连接问题
- 检查网络是否能访问 Azure 服务
- 确认 API 密钥是否正确
- 如需更换 API 配置，修改 `app.py` 中的 `AZURE_CONFIG`

## 使用技巧

### 1. 调试模式
`app.py` 默认开启了调试模式，修改代码后会自动重载。

### 2. 查看日志
在 PyCharm 的运行窗口可以看到所有请求日志和错误信息。

### 3. 数据查看
- 对话记录保存在 `data/` 目录
- 可以直接用 PyCharm 打开查看 JSON 文件

### 4. 快捷键
- `Shift + F10`：运行
- `Shift + F9`：调试
- `Ctrl + Shift + F10`：运行当前文件

## 项目结构说明

```
hr_chatbot/
├── app.py              # 主程序（包含所有功能）
├── requirements.txt    # 依赖列表
├── README.md          # 项目说明
├── PYCHARM_GUIDE.md   # 本文件
├── data/              # 数据目录（自动创建）
│   └── session_*.json # 会话记录文件
└── .gitignore         # Git忽略文件
```

## 开发建议

1. **修改提示词**：在 `app.py` 中找到 `PATIENT_SYSTEM_PROMPT` 和 `EVALUATION_SYSTEM_PROMPT`
2. **添加症状**：修改 `INITIAL_SYMPTOMS` 列表
3. **调整评分标准**：修改 `EVALUATION_SYSTEM_PROMPT` 中的评分说明
4. **更改界面样式**：修改 `HTML_TEMPLATE` 中的 CSS

## 部署说明

如果需要部署到服务器：
1. 将 `debug=True` 改为 `debug=False`
2. 使用 `gunicorn` 或其他 WSGI 服务器
3. 配置反向代理（如 Nginx）

## 联系支持

如有技术问题，请在 GitHub 上提交 Issue。