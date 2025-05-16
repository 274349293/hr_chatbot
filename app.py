import os
import json
import uuid
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from openai import AzureOpenAI
import random

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("hr_chatbot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("HR_Chatbot")

app = Flask(__name__)
CORS(app)

logger.info("===============================================")
logger.info("汇仁医药客服训练系统初始化开始")
logger.info("===============================================")

# Azure OpenAI 配置
AZURE_CONFIG = {
    "api_key": "5fea49cd1d9b404598ed9d2259738486",
    "endpoint": "https://ll274349293.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?",
    "api_version": "2024-08-01-preview",
    "model": "gpt-4o-mini"
}
logger.info(f"Azure OpenAI配置: 模型={AZURE_CONFIG['model']}, API版本={AZURE_CONFIG['api_version']}")

# 创建 Azure OpenAI 客户端
try:
    client = AzureOpenAI(
        api_key=AZURE_CONFIG["api_key"],
        azure_endpoint=AZURE_CONFIG["endpoint"],
        api_version=AZURE_CONFIG["api_version"]
    )
    logger.info("Azure OpenAI客户端创建成功")
except Exception as e:
    logger.error(f"Azure OpenAI客户端创建失败: {str(e)}")
    raise

# 加载产品配置
try:
    logger.info("开始加载产品配置文件")
    with open('product_config.json', 'r', encoding='utf-8') as f:
        PRODUCT_CONFIG = json.load(f)
    logger.info(f"产品配置加载成功, 共有{len(PRODUCT_CONFIG['products'])}个产品")
    for product_name in PRODUCT_CONFIG["products"].keys():
        logger.info(f"产品: {product_name}")
except Exception as e:
    logger.error(f"产品配置加载失败: {str(e)}")
    raise

# 获取每个产品的初始症状
INITIAL_SYMPTOMS = []
try:
    logger.info("开始提取产品初始症状")
    for product_name, product_info in PRODUCT_CONFIG["products"].items():
        if "initial_symptom" in product_info:
            INITIAL_SYMPTOMS.append({
                "product": product_name,
                "symptom": product_info["initial_symptom"]
            })
            logger.info(f"产品[{product_name}]的初始症状: {product_info['initial_symptom']}")
    logger.info(f"共提取了{len(INITIAL_SYMPTOMS)}个产品的初始症状")
except Exception as e:
    logger.error(f"提取产品初始症状失败: {str(e)}")
    raise

# 系统提示词配置
PATIENT_SYSTEM_PROMPT = """你是一位正在寻求购药建议的普通患者。你的任务是模拟真实的患者行为，向药店在线客服咨询并购买药品。你应该：
1. 描述自己的症状，使用口语化表达，避免专业用语
2. 表现出对病情的适度担心和困惑，像真实病人一样表达不适
3. 询问药品的效果、副作用、价格等信息，就像不懂医学的普通人
4. 可以适当表现出犹豫或比较不同药品
5. A的语言要非常口语化、自然，用词口语化，可以有些语气词，像真人聊天一样

记住：你是在与汇仁医药的在线客服对话。汇仁医药的主要产品包括：
- 汇仁肾宝片：用于调和阴阳，温阳补肾，扶正固本。用于腰腿酸痛，精神不振，夜尿频多，畏寒怕冷；妇女白带清稀。
- 六味地黄丸：用于滋阴补肾。用于肾阴亏损，头晕耳鸣，腰膝酸软，骨蒸潮热，盗汗遗精。
- 女金胶囊：用于调经养血，理气止痛。用于月经量少、后错，痛经，小腹胀痛，腰腿酸痛。

你的目标是让客服向你推荐目标产品，询问相关信息并最终购买产品。

当客服建议了产品，表现得像是考虑要购买，问一些价格、用法或副作用等问题。最终表现出愿意购买的意向。
"""
logger.info("系统提示词配置完成")

# 评分系统提示词模板
EVALUATION_SYSTEM_PROMPT_TEMPLATE = """你是一位专业的客服质量评估专家，同时也是医药专业人士。请根据以下对话记录及产品信息，评估客服人员的表现。

评分标准包括：
1. 专业性（30分）：产品知识掌握程度、医学常识准确性、产品信息描述是否符合实际情况
2. 沟通能力（25分）：语言表达清晰度、同理心、耐心程度、是否理解患者需求
3. 解决问题能力（25分）：理解客户需求、提供合适建议、处理异议、是否正确推荐了目标产品
4. 服务态度（20分）：礼貌程度、主动性、服务意识、回复速度

目标产品信息：
{product_info}

请给出总分（满分100分）和具体评价，指出优点和需要改进的地方。尤其要注意客服对产品信息描述的准确性。
如果客服描述的产品信息（如价格、用法用量、功效等）与实际不符，请在评价中指出并扣分。
如果客服未能成功推荐目标产品或推荐了错误的产品，请扣除相应分数。

输出格式为JSON：
{{
    "total_score": 85,
    "professionalism": 88,
    "communication": 82,
    "problem_solving": 85,
    "service_attitude": 83,
    "strengths": ["回应及时", "产品知识扎实"],
    "improvements": ["可以更主动询问顾客需求", "解释可以更通俗易懂"],
    "overall_comment": "整体表现良好，专业知识扎实，建议加强主动服务意识。"
}}
"""
logger.info("评分系统提示词模板配置完成")

# 存储当前会话的数据
sessions = {}
logger.info("会话存储初始化完成")

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
        .target-product {
            color: #ff5722;
            font-weight: bold;
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
                    <p><span class="target-product">目标产品：${evaluation.target_product || "未指定"}</span></p>
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
                            ${session.target_product ? `<div>目标产品: ${session.target_product}</div>` : ''}
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
logger.info("HTML模板配置完成")


@app.route('/')
def index():
    """返回前端页面"""
    logger.info("访问首页")
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/start_chat', methods=['POST'])
def start_chat():
    """开始新的聊天会话"""
    logger.info("请求开始新的聊天会话")

    # 生成会话ID
    session_id = str(uuid.uuid4())
    logger.info(f"生成会话ID: {session_id}")

    # 随机选择一个产品及其对应的初始症状
    chosen_product_data = random.choice(INITIAL_SYMPTOMS)
    target_product = chosen_product_data["product"]
    initial_symptom_template = chosen_product_data["symptom"]
    logger.info(f"随机选择的目标产品: {target_product}")

    # 让AI生成更自然的开场白
    try:
        # 构建开场白生成提示
        open_messages = [
            {"role": "system", "content": """你是一位帮助生成自然、口语化患者开场白的助手。
请基于给定的症状模板，生成一个听起来像真实患者的开场白。使用口语化表达，添加适当的语气词，
让内容听起来像是一个普通人在描述自己的不适，而不是机器人或医学专业人士。
确保保留原始症状的核心信息，但表达方式更加自然、口语化。不要使用专业医学术语。"""},
            {"role": "user", "content": f"请基于这个症状描述生成一个自然的患者开场白: {initial_symptom_template}"}
        ]
        logger.info(f"准备生成更自然的开场白")

        # 调用AI生成开场白
        response = client.chat.completions.create(
            model=AZURE_CONFIG["model"],
            messages=open_messages,
            temperature=0.8,
            max_tokens=300
        )

        # 获取生成的开场白
        initial_symptom = response.choices[0].message.content.strip()
        logger.info(f"成功生成自然的开场白: {initial_symptom}")
    except Exception as e:
        # 如果生成失败，使用原始模板
        logger.error(f"生成开场白失败，使用原始模板: {str(e)}")
        initial_symptom = initial_symptom_template

    logger.info(f"最终使用的开场白: {initial_symptom}")

    # 初始化会话数据
    sessions[session_id] = {
        'id': session_id,
        'messages': [
            {'role': 'patient', 'content': initial_symptom}
        ],
        'timestamp': datetime.now().isoformat(),
        'status': 'active',
        'target_product': target_product
    }
    logger.info(f"会话[{session_id}]初始化成功")

    return jsonify({
        'session_id': session_id,
        'initial_message': initial_symptom,
        'target_product': target_product
    })


@app.route('/api/send_message')
def send_message():
    """处理用户消息并返回AI响应（流式）"""
    session_id = request.args.get('session_id')
    user_message = request.args.get('message')
    logger.info(f"接收到会话[{session_id}]的新消息")

    if not session_id or not user_message:
        logger.error("缺少必要参数: session_id或message")
        return jsonify({'error': '缺少必要参数'}), 400

    # 保存用户消息
    sessions[session_id]['messages'].append({
        'role': 'customer-service',
        'content': user_message
    })
    logger.info(f"会话[{session_id}]保存了客服消息: {user_message}")

    # 获取目标产品信息
    target_product = sessions[session_id].get('target_product')
    product_info = PRODUCT_CONFIG["products"].get(target_product, {})
    logger.info(f"会话[{session_id}]的目标产品: {target_product}")

    # 构建对话历史
    messages = [
        {"role": "system", "content": PATIENT_SYSTEM_PROMPT},
    ]

    # 如果有目标产品，添加到提示词中
    if target_product:
        additional_prompt = f"""
你的目标产品是：{target_product}。
请自然地引导客服推荐这个产品，但不要直接说出产品名称。可以描述与这个产品相关的症状，询问类似效果的药品。
"""
        messages[0]["content"] += additional_prompt
        logger.info(f"为会话[{session_id}]添加了目标产品提示")

    for msg in sessions[session_id]['messages']:
        role = "assistant" if msg['role'] == "patient" else "user"
        messages.append({"role": role, "content": msg['content']})

    logger.info(f"会话[{session_id}]构建了完整对话历史，共{len(messages)}条消息")

    def generate():
        """生成流式响应"""
        try:
            # 获取AI响应
            logger.info(f"开始调用Azure OpenAI生成会话[{session_id}]的患者回复")
            response = client.chat.completions.create(
                model=AZURE_CONFIG["model"],
                messages=messages,
                temperature=0.85,
                max_tokens=1200,
                stream=True
            )
            logger.info(f"成功创建会话[{session_id}]的流式响应请求")

            full_response = ""
            chunk_count = 0
            for chunk in response:
                chunk_count += 1
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content})}\n\n"

            logger.info(f"会话[{session_id}]的流式响应完成，共收到{chunk_count}个响应块")
            logger.debug(f"会话[{session_id}]的完整患者回复: {full_response}")

            # 保存AI响应
            sessions[session_id]['messages'].append({
                'role': 'patient',
                'content': full_response
            })
            logger.info(f"会话[{session_id}]保存了患者回复")

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            logger.error(f"会话[{session_id}]生成响应出错: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return app.response_class(generate(), mimetype='text/event-stream')


@app.route('/api/end_chat', methods=['POST'])
def end_chat():
    """结束聊天并获取评分"""
    data = request.json
    session_id = data.get('session_id')
    logger.info(f"请求结束会话[{session_id}]并评分")

    if not session_id:
        logger.error("缺少会话ID")
        return jsonify({'error': '缺少会话ID'}), 400

    # 获取对话记录
    messages = sessions[session_id]['messages']
    target_product = sessions[session_id].get('target_product', '未知产品')
    logger.info(f"会话[{session_id}]的目标产品是: {target_product}")
    logger.info(f"会话[{session_id}]共有{len(messages)}条消息记录")

    # 获取目标产品的详细信息
    product_info = ""
    if target_product in PRODUCT_CONFIG["products"]:
        product_data = PRODUCT_CONFIG["products"][target_product]

        # 格式化产品详细信息
        product_info = f"产品名称: {target_product}\n"

        # 添加产品说明
        if "产品说明" in product_data:
            product_info += "产品说明:\n"
            for key, value in product_data["产品说明"].items():
                if isinstance(value, list):
                    product_info += f"- {key}: \n"
                    for item in value:
                        product_info += f"  * {item}\n"
                else:
                    product_info += f"- {key}: {value}\n"

        # 添加价目表
        if "价目表" in product_data:
            product_info += "价目表:\n"
            for item in product_data["价目表"]:
                product_info += f"- 规格: {item.get('商品规格', '未知')}，价格: {item.get('零售价', '未知')}元\n"

    logger.info(f"获取到产品[{target_product}]的详细信息")
    logger.debug(f"产品详细信息: {product_info}")

    # 生成包含产品信息的评分系统提示词
    evaluation_prompt = EVALUATION_SYSTEM_PROMPT_TEMPLATE.format(product_info=product_info)
    logger.info(f"生成了包含产品信息的评分系统提示词")

    # 构建评价请求
    conversation_text = "\n".join([
        f"{'客服' if msg['role'] == 'customer-service' else '患者'}: {msg['content']}"
        for msg in messages
    ])
    logger.info(f"生成会话[{session_id}]的对话文本, 长度: {len(conversation_text)}")

    eval_messages = [
        {"role": "system", "content": evaluation_prompt},
        {"role": "user",
         "content": f"请评价以下客服对话记录：\n\n{conversation_text}\n\n客服应推荐的目标产品是：{target_product}"}
    ]
    logger.info(f"构建会话[{session_id}]的评价请求")

    try:
        # 获取评价
        logger.info(f"开始调用Azure OpenAI评价会话[{session_id}]")
        response = client.chat.completions.create(
            model=AZURE_CONFIG["model"],
            messages=eval_messages,
            temperature=0.3,
            max_tokens=1000
        )
        logger.info(f"成功获取会话[{session_id}]的评价响应")

        # 解析评价结果
        eval_text = response.choices[0].message.content
        logger.debug(f"会话[{session_id}]的原始评价文本: {eval_text}")

        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', eval_text, re.DOTALL)
            if json_match:
                logger.info(f"从代码块中提取会话[{session_id}]的评价JSON")
                evaluation = json.loads(json_match.group(1))
            else:
                # 如果没有找到JSON格式，尝试直接解析
                logger.info(f"直接解析会话[{session_id}]的评价JSON")
                evaluation = json.loads(eval_text)
            logger.info(f"会话[{session_id}]的评价解析成功: {evaluation}")
        except Exception as e:
            logger.error(f"会话[{session_id}]的评价结果解析失败: {str(e)}")
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
            logger.info(f"使用默认评价结果: {evaluation}")
    except Exception as e:
        logger.error(f"会话[{session_id}]评价出错: {str(e)}")
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
        logger.info(f"由于错误使用备用评价结果: {evaluation}")

    # 添加目标产品信息到评价中
    evaluation["target_product"] = target_product
    logger.info(f"向会话[{session_id}]的评价结果添加目标产品信息")

    # 更新会话状态并保存
    sessions[session_id]['status'] = 'completed'
    sessions[session_id]['evaluation'] = evaluation
    sessions[session_id]['score'] = evaluation['total_score']
    logger.info(f"更新会话[{session_id}]状态为已完成，评分: {evaluation['total_score']}")

    # 保存到文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"session_{session_id}_{timestamp}.json"
    logger.info(f"准备将会话[{session_id}]保存到文件: {filename}")

    # 确保data目录存在
    os.makedirs('data', exist_ok=True)
    logger.info("确认data目录存在")

    with open(f'data/{filename}', 'w', encoding='utf-8') as f:
        json.dump(sessions[session_id], f, ensure_ascii=False, indent=2)
    logger.info(f"会话[{session_id}]已保存到文件: data/{filename}")

    return jsonify({
        'evaluation': evaluation
    })


@app.route('/api/sessions')
def get_sessions():
    """获取所有会话列表"""
    logger.info("请求获取所有会话列表")

    # 从内存中获取会话
    session_list = []
    for session_id, session in sessions.items():
        session_list.append({
            'id': session_id,
            'timestamp': session['timestamp'],
            'score': session.get('score'),
            'status': session.get('status', 'active'),
            'target_product': session.get('target_product', '未知产品')
        })
    logger.info(f"内存中共有{len(session_list)}个会话")

    # 从文件中加载历史会话
    loaded_count = 0
    if os.path.exists('data'):
        logger.info("开始从data目录加载历史会话")
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
                                'status': session_data.get('status', 'completed'),
                                'target_product': session_data.get('target_product', '未知产品')
                            })
                            loaded_count += 1
                except Exception as e:
                    logger.error(f"加载会话文件出错 {filename}: {str(e)}")
        logger.info(f"从文件中成功加载了{loaded_count}个历史会话")
    else:
        logger.warning("data目录不存在，未加载历史会话")

    # 按时间排序
    session_list.sort(key=lambda x: x['timestamp'], reverse=True)
    logger.info(f"总共返回{len(session_list)}个会话记录")

    return jsonify({'sessions': session_list})


@app.route('/api/session/<session_id>')
def get_session(session_id):
    """获取特定会话的详情"""
    logger.info(f"请求获取会话[{session_id}]的详情")

    # 先从内存中查找
    if session_id in sessions:
        logger.info(f"从内存中找到会话[{session_id}]")
        return jsonify(sessions[session_id])

    # 从文件中查找
    if os.path.exists('data'):
        logger.info(f"在内存中未找到会话[{session_id}]，开始从文件查找")
        for filename in os.listdir('data'):
            if filename.endswith('.json') and session_id in filename:
                try:
                    logger.info(f"在文件{filename}中找到会话[{session_id}]")
                    with open(f'data/{filename}', 'r', encoding='utf-8') as f:
                        return jsonify(json.load(f))
                except Exception as e:
                    logger.error(f"加载会话文件出错 {filename}: {str(e)}")

    logger.error(f"会话[{session_id}]不存在")
    return jsonify({'error': '会话不存在'}), 404


if __name__ == '__main__':
    logger.info("汇仁医药客服训练系统")
    logger.info("====================")
    logger.info("启动中...")
    logger.info("访问地址: http://localhost:5000")
    logger.info("按 Ctrl+C 停止服务")

    # 确保data目录存在
    os.makedirs('data', exist_ok=True)
    logger.info("确保data目录存在")

    # 启动Flask应用
    logger.info("开始启动Flask应用")
    app.run(debug=True, port=5000, threaded=True)