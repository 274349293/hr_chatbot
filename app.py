import os
import json
import uuid
import threading
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from openai import AzureOpenAI
import random

app = Flask(__name__)
CORS(app)

# Azure OpenAI 配置
AZURE_CONFIG = {
    "api_key": "5fea49cd1d9b404598ed9d2259738486",
    "endpoint": "https://ll274349293.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?",
    "api_version": "2024-08-01-preview",
    "model": "gpt-4o-mini"
}

# 创建 Azure OpenAI 客户端
client = AzureOpenAI(
    api_key=AZURE_CONFIG["api_key"],
    azure_endpoint=AZURE_CONFIG["endpoint"],
    api_version=AZURE_CONFIG["api_version"]
)

# 系统提示词配置
PATIENT_SYSTEM_PROMPT = """你是一位正在寻求购药建议的患者。你的任务是模拟真实的患者行为，向药店在线客服咨询并购买药品。你应该：
1. 描述自己的症状，但不要太专业
2. 表现出对病情的适度担心
3. 询问药品的效果、副作用、价格等信息
4. 可以适当表现出犹豫或比较不同药品
5. 语言要口语化、自然

记住：你是在与汇仁医药的在线客服对话。汇仁医药的主要产品包括：
- 肾宝片：用于肾虚所致的腰膝酸软、精神不振、夜尿频多等症状
- 女金片：用于月经不调、痛经等妇科问题
- 脑心舒口服液：用于心脑血管疾病的辅助治疗
- 安神补脑液：用于失眠、健忘、头晕等症状
"""

# 初始症状列表
INITIAL_SYMPTOMS = [
    "最近总是腰酸背痛，晚上起夜次数也多了，感觉整个人没什么精神。",
    "这两个月月经一直不太规律，还经常肚子疼，想问问有什么药可以调理一下。",
    "最近工作压力大，经常失眠，白天头晕乏力，想买点药改善一下。",
    "父亲有高血压，最近总说头晕心慌，想给他买点保健品。",
    "孩子最近学习压力大，记忆力好像下降了，有什么补脑的产品吗？"
]

# 评分系统提示词
EVALUATION_SYSTEM_PROMPT = """你是一位专业的客服质量评估专家。请根据以下对话记录，评估客服人员的表现。评分标准包括：
1. 专业性（30分）：产品知识掌握程度、医学常识准确性
2. 沟通能力（25分）：语言表达清晰度、同理心、耐心程度
3. 解决问题能力（25分）：理解客户需求、提供合适建议、处理异议
4. 服务态度（20分）：礼貌程度、主动性、服务意识

请给出总分（满分100分）和具体评价，指出优点和需要改进的地方。
输出格式为JSON：
{
    "total_score": 85,
    "professionalism": 88,
    "communication": 82,
    "problem_solving": 85,
    "service_attitude": 83,
    "strengths": ["回应及时", "产品知识扎实"],
    "improvements": ["可以更主动询问顾客需求", "解释可以更通俗易懂"],
    "overall_comment": "整体表现良好，专业知识扎实，建议加强主动服务意识。"
}
"""

# 存储当前会话的数据
sessions = {}

# HTML模板（简单的单页面应用）
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>汇仁医药客服训练系统</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background-color: #f5f5f5;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background-color: #2c3e50;
            color: white;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .container {
            flex: 1;
            display: flex;
            max-width: 1200px;
            margin: 0 auto;
            width: 100%;
            padding: 20px;
            gap: 20px;
        }
        .sidebar {
            width: 250px;
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        .chat-container {
            flex: 1;
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
        }
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .message {
            max-width: 70%;
            padding: 10px 15px;
            border-radius: 10px;
            word-wrap: break-word;
        }
        .message.patient {
            align-self: flex-start;
            background-color: #e9ecef;
        }
        .message.customer-service {
            align-self: flex-end;
            background-color: #007bff;
            color: white;
        }
        .input-area {
            display: flex;
            gap: 10px;
            padding: 20px;
            border-top: 1px solid #eee;
        }
        .input-area input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        .input-area button {
            padding: 10px 20px;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
        }
        .input-area button:hover {
            background-color: #0056b3;
        }
        .button {
            padding: 10px 20px;
            background-color: #28a745;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            margin: 10px 0;
            width: 100%;
            font-size: 16px;
        }
        .button:hover {
            background-color: #218838;
        }
        .button.danger {
            background-color: #dc3545;
        }
        .button.danger:hover {
            background-color: #c82333;
        }
        .session-list {
            margin-top: 20px;
        }
        .session-item {
            padding: 10px;
            margin: 5px 0;
            background-color: #f8f9fa;
            border-radius: 5px;
            cursor: pointer;
        }
        .session-item:hover {
            background-color: #e9ecef;
        }
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: rgba(0,0,0,0.5);
            justify-content: center;
            align-items: center;
        }
        .modal-content {
            background: white;
            padding: 30px;
            border-radius: 10px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }
        .score-section {
            margin: 15px 0;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
        .score-label {
            font-weight: bold;
            margin-right: 10px;
        }
        .close-button {
            float: right;
            cursor: pointer;
            font-size: 24px;
            color: #999;
        }
        .close-button:hover {
            color: #333;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>汇仁医药客服训练系统</h1>
        <div id="session-info"></div>
    </div>

    <div class="container">
        <div class="sidebar">
            <button class="button" onclick="startNewChat()">开始新对话</button>
            <div class="session-list" id="session-list">
                <h3>历史会话</h3>
            </div>
        </div>

        <div class="main-content">
            <div class="chat-container">
                <div class="messages" id="messages">
                    <div style="text-align: center; color: #666; padding: 50px;">
                        点击"开始新对话"开始训练
                    </div>
                </div>
                <div class="input-area" id="input-area" style="display: none;">
                    <input type="text" id="message-input" placeholder="输入您的回复..." onkeypress="handleKeyPress(event)">
                    <button onclick="sendMessage()">发送</button>
                    <button class="danger" onclick="endChat()">结束对话</button>
                </div>
            </div>
        </div>
    </div>

    <div class="modal" id="evaluation-modal">
        <div class="modal-content">
            <span class="close-button" onclick="closeModal()">&times;</span>
            <h2>服务质量评价</h2>
            <div id="evaluation-content"></div>
        </div>
    </div>

    <script>
        let currentSessionId = null;
        let isActive = false;

        function startNewChat() {
            fetch('/api/start_chat', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    currentSessionId = data.session_id;
                    isActive = true;
                    document.getElementById('messages').innerHTML = '';
                    addMessage(data.initial_message, 'patient');
                    document.getElementById('input-area').style.display = 'flex';
                    updateSessionInfo();
                    loadSessions();
                });
        }

        function sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            if (!message || !isActive) return;

            addMessage(message, 'customer-service');
            input.value = '';

            const messageDiv = document.createElement('div');
            messageDiv.className = 'message patient';
            messageDiv.innerHTML = '正在输入...';
            document.getElementById('messages').appendChild(messageDiv);

            const eventSource = new EventSource(`/api/send_message?session_id=${currentSessionId}&message=${encodeURIComponent(message)}`);
            let fullResponse = '';

            eventSource.onmessage = function(event) {
                const data = JSON.parse(event.data);
                if (data.content) {
                    fullResponse += data.content;
                    messageDiv.innerHTML = fullResponse;
                    document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
                }
                if (data.done) {
                    eventSource.close();
                }
            };

            eventSource.onerror = function(error) {
                console.error('SSE Error:', error);
                eventSource.close();
                messageDiv.innerHTML = fullResponse || '发送失败，请重试';
            };
        }

        function endChat() {
            if (!currentSessionId || !isActive) return;

            fetch('/api/end_chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: currentSessionId })
            })
            .then(response => response.json())
            .then(data => {
                isActive = false;
                document.getElementById('input-area').style.display = 'none';
                showEvaluation(data.evaluation);
                loadSessions();
            });
        }

        function showEvaluation(evaluation) {
            const content = `
                <div class="score-section">
                    <h3>总分: ${evaluation.total_score}分</h3>
                </div>
                <div class="score-section">
                    <span class="score-label">专业性:</span>${evaluation.professionalism}分<br>
                    <span class="score-label">沟通能力:</span>${evaluation.communication}分<br>
                    <span class="score-label">解决问题能力:</span>${evaluation.problem_solving}分<br>
                    <span class="score-label">服务态度:</span>${evaluation.service_attitude}分
                </div>
                <div class="score-section">
                    <h4>优点:</h4>
                    <ul>${evaluation.strengths.map(s => `<li>${s}</li>`).join('')}</ul>
                </div>
                <div class="score-section">
                    <h4>待改进:</h4>
                    <ul>${evaluation.improvements.map(i => `<li>${i}</li>`).join('')}</ul>
                </div>
                <div class="score-section">
                    <h4>总体评价:</h4>
                    <p>${evaluation.overall_comment}</p>
                </div>
            `;
            document.getElementById('evaluation-content').innerHTML = content;
            document.getElementById('evaluation-modal').style.display = 'flex';
        }

        function closeModal() {
            document.getElementById('evaluation-modal').style.display = 'none';
        }

        function loadSessions() {
            fetch('/api/sessions')
                .then(response => response.json())
                .then(data => {
                    const sessionList = document.getElementById('session-list');
                    sessionList.innerHTML = '<h3>历史会话</h3>';
                    data.sessions.forEach(session => {
                        const item = document.createElement('div');
                        item.className = 'session-item';
                        item.innerHTML = `
                            <div>${new Date(session.timestamp).toLocaleString()}</div>
                            <div>得分: ${session.score || '未评分'}</div>
                        `;
                        item.onclick = () => viewSession(session.id);
                        sessionList.appendChild(item);
                    });
                });
        }

        function viewSession(sessionId) {
            fetch(`/api/session/${sessionId}`)
                .then(response => response.json())
                .then(data => {
                    currentSessionId = sessionId;
                    isActive = false;
                    const messagesDiv = document.getElementById('messages');
                    messagesDiv.innerHTML = '';

                    data.messages.forEach(msg => {
                        addMessage(msg.content, msg.role);
                    });

                    document.getElementById('input-area').style.display = 'none';
                    if (data.evaluation) {
                        showEvaluation(data.evaluation);
                    }
                });
        }

        function addMessage(content, role) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}`;
            messageDiv.textContent = content;
            document.getElementById('messages').appendChild(messageDiv);
            document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
        }

        function updateSessionInfo() {
            document.getElementById('session-info').innerHTML = currentSessionId ? 
                `会话ID: ${currentSessionId.substring(0, 8)}...` : '';
        }

        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }

        // 页面加载时加载历史会话
        window.onload = function() {
            loadSessions();
        };
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    """返回前端页面"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/start_chat', methods=['POST'])
def start_chat():
    """开始新的聊天会话"""
    session_id = str(uuid.uuid4())
    initial_symptom = random.choice(INITIAL_SYMPTOMS)

    # 初始化会话数据
    sessions[session_id] = {
        'id': session_id,
        'messages': [
            {'role': 'patient', 'content': initial_symptom}
        ],
        'timestamp': datetime.now().isoformat(),
        'status': 'active'
    }

    return jsonify({
        'session_id': session_id,
        'initial_message': initial_symptom
    })


@app.route('/api/send_message')
def send_message():
    """处理用户消息并返回AI响应（流式）"""
    session_id = request.args.get('session_id')
    user_message = request.args.get('message')

    if not session_id or not user_message:
        return jsonify({'error': '缺少必要参数'}), 400

    # 保存用户消息
    sessions[session_id]['messages'].append({
        'role': 'customer-service',
        'content': user_message
    })

    # 构建对话历史
    messages = [
        {"role": "system", "content": PATIENT_SYSTEM_PROMPT},
    ]

    for msg in sessions[session_id]['messages']:
        role = "assistant" if msg['role'] == "patient" else "user"
        messages.append({"role": role, "content": msg['content']})

    def generate():
        """生成流式响应"""
        try:
            # 获取AI响应
            response = client.chat.completions.create(
                model=AZURE_CONFIG["model"],
                messages=messages,
                temperature=0.85,
                max_tokens=1200,
                stream=True
            )

            full_response = ""
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content})}\n\n"

            # 保存AI响应
            sessions[session_id]['messages'].append({
                'role': 'patient',
                'content': full_response
            })

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return app.response_class(generate(), mimetype='text/event-stream')


@app.route('/api/end_chat', methods=['POST'])
def end_chat():
    """结束聊天并获取评分"""
    data = request.json
    session_id = data.get('session_id')

    if not session_id:
        return jsonify({'error': '缺少会话ID'}), 400

    # 获取对话记录
    messages = sessions[session_id]['messages']

    # 构建评价请求
    conversation_text = "\n".join([
        f"{'客服' if msg['role'] == 'customer-service' else '患者'}: {msg['content']}"
        for msg in messages
    ])

    eval_messages = [
        {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
        {"role": "user", "content": f"请评价以下客服对话记录：\n\n{conversation_text}"}
    ]

    try:
        # 获取评价
        response = client.chat.completions.create(
            model=AZURE_CONFIG["model"],
            messages=eval_messages,
            temperature=0.3,
            max_tokens=1000
        )

        # 解析评价结果
        eval_text = response.choices[0].message.content
        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', eval_text, re.DOTALL)
            if json_match:
                evaluation = json.loads(json_match.group(1))
            else:
                # 如果没有找到JSON格式，尝试直接解析
                evaluation = json.loads(eval_text)
        except:
            # 如果解析失败，返回默认评价
            evaluation = {
                "total_score": 75,
                "professionalism": 75,
                "communication": 75,
                "problem_solving": 75,
                "service_attitude": 75,
                "strengths": ["回应及时", "态度友好"],
                "improvements": ["可以更深入了解客户需求", "产品知识可以更全面"],
                "overall_comment": "客服表现中规中矩，有进步空间。"
            }
    except Exception as e:
        print(f"评价出错: {e}")
        evaluation = {
            "total_score": 75,
            "professionalism": 75,
            "communication": 75,
            "problem_solving": 75,
            "service_attitude": 75,
            "strengths": ["回应及时"],
            "improvements": ["系统出错，无法准确评价"],
            "overall_comment": "评价系统出现错误，请稍后重试。"
        }

    # 更新会话状态并保存
    sessions[session_id]['status'] = 'completed'
    sessions[session_id]['evaluation'] = evaluation
    sessions[session_id]['score'] = evaluation['total_score']

    # 保存到文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"session_{session_id}_{timestamp}.json"

    # 确保data目录存在
    os.makedirs('data', exist_ok=True)

    with open(f'data/{filename}', 'w', encoding='utf-8') as f:
        json.dump(sessions[session_id], f, ensure_ascii=False, indent=2)

    return jsonify({
        'evaluation': evaluation
    })


@app.route('/api/sessions')
def get_sessions():
    """获取所有会话列表"""
    # 从内存中获取会话
    session_list = []
    for session_id, session in sessions.items():
        session_list.append({
            'id': session_id,
            'timestamp': session['timestamp'],
            'score': session.get('score'),
            'status': session.get('status', 'active')
        })

    # 从文件中加载历史会话
    if os.path.exists('data'):
        for filename in os.listdir('data'):
            if filename.endswith('.json') and filename.startswith('session_'):
                try:
                    with open(f'data/{filename}', 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                        # 避免重复添加
                        if session_data['id'] not in sessions:
                            session_list.append({
                                'id': session_data['id'],
                                'timestamp': session_data['timestamp'],
                                'score': session_data.get('score'),
                                'status': session_data.get('status', 'completed')
                            })
                except Exception as e:
                    print(f"加载会话文件出错 {filename}: {e}")

    # 按时间排序
    session_list.sort(key=lambda x: x['timestamp'], reverse=True)

    return jsonify({'sessions': session_list})


@app.route('/api/session/<session_id>')
def get_session(session_id):
    """获取特定会话的详情"""
    # 先从内存中查找
    if session_id in sessions:
        return jsonify(sessions[session_id])

    # 从文件中查找
    if os.path.exists('data'):
        for filename in os.listdir('data'):
            if filename.endswith('.json') and session_id in filename:
                try:
                    with open(f'data/{filename}', 'r', encoding='utf-8') as f:
                        return jsonify(json.load(f))
                except Exception as e:
                    print(f"加载会话文件出错 {filename}: {e}")

    return jsonify({'error': '会话不存在'}), 404


if __name__ == '__main__':
    print("汇仁医药客服训练系统")
    print("====================")
    print("启动中...")
    print("\n访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务\n")

    # 确保data目录存在
    os.makedirs('data', exist_ok=True)

    # 启动Flask应用
    app.run(debug=True, port=5000, threaded=True)
