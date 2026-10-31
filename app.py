import os
import json
import time
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# 指向与 bot.py 共用的状态通讯档案
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(CURRENT_DIR, 'bot_bridge_status.json')
COMMAND_FILE = os.path.join(CURRENT_DIR, 'bot_bridge_command.json')

STANDALONE_UI_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Novis ui - 苹果生态系独立控制台</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --apple-bg: #000000;
            --apple-card: rgba(255, 255, 255, 0.045);
            --apple-card-hover: rgba(255, 255, 255, 0.08);
            --apple-border: rgba(255, 255, 255, 0.1);
            --apple-blue: #0a84ff;
            --apple-green: #32d74b;
            --apple-ease: cubic-bezier(0.25, 1, 0.5, 1);
        }

        body { 
            background-color: var(--apple-bg); 
            color: #f5f5f7; 
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Icons", "Helvetica Neue", Arial, sans-serif; 
            min-height: 100vh; 
            overflow-x: hidden; 
            -webkit-font-smoothing: antialiased;
            font-size: 1.05rem; /* 整体放大 5% */
        }
        
        /* 离线等待遮罩动画 */
        #offline-overlay {
            position: fixed;
            top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0, 0, 0, 0.9);
            backdrop-filter: blur(40px);
            -webkit-backdrop-filter: blur(40px);
            z-index: 9999;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 20px;
            transition: opacity 0.5s var(--apple-ease);
        }
        .offline-card {
            background: var(--apple-card);
            border: 1px solid var(--apple-border);
            border-radius: 26px;
            padding: 42px;
            text-align: center;
            max-width: 460px;
            width: 100%;
            box-shadow: 0 25px 50px rgba(0,0,0,0.7);
            animation: appleFloat 3s infinite var(--apple-ease);
        }
        @keyframes appleFloat {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-8px); }
        }

        /* 侧边栏基础设定 (支持多端响应式) */
        .sidebar { 
            background: rgba(15, 19, 26, 0.9); 
            backdrop-filter: blur(30px);
            -webkit-backdrop-filter: blur(30px);
            width: 285px; /* 放大 5% */
            height: 100vh; 
            position: fixed; 
            top: 0; 
            left: 0; 
            border-right: 1px solid var(--apple-border); 
            display: flex; 
            flex-direction: column; 
            z-index: 1050; 
            transition: transform 0.4s var(--apple-ease); 
        }
        .sidebar-brand { 
            padding: 34px 26px; 
            font-size: 1.6rem; 
            font-weight: 700; 
            color: #ffffff; 
            display: flex; 
            align-items: center; 
            gap: 15px; 
        }
        .sidebar-menu { list-style: none; padding: 0 14px; margin: 0; }
        .sidebar-menu li a { 
            display: flex; align-items: center; gap: 17px; 
            padding: 16px 22px; color: #86868b; 
            text-decoration: none; font-weight: 500; font-size: 15.2px; /* 放大 5% */
            border-radius: 13px; margin-bottom: 8px; cursor: pointer; 
            transition: 0.3s var(--apple-ease);
        }
        .sidebar-menu li a:hover { background-color: rgba(255, 255, 255, 0.07); color: #ffffff; transform: translateX(5px); }
        .sidebar-menu li a.active { background-color: var(--apple-blue); color: #ffffff; box-shadow: 0 6px 22px rgba(10, 132, 255, 0.45); }

        /* 主内容区域響應式 Margin */
        .main-content { 
            margin-left: 285px; 
            min-height: 100vh; 
            padding: 42px; 
            background-color: #0b0e14; 
            transition: margin 0.4s var(--apple-ease); 
        }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 42px; flex-wrap: wrap; gap: 20px; }

        /* 手机/平板顶栏菜单按钮 (默认隐藏，小屏幕显示) */
        .mobile-header { 
            display: none; 
            background: rgba(15, 19, 26, 0.9); 
            backdrop-filter: blur(25px);
            padding: 16px 22px; 
            border-bottom: 1px solid var(--apple-border); 
            align-items: center; 
            justify-content: space-between; 
            margin-bottom: 28px; 
            border-radius: 16px; 
        }

        /* 侧边栏遮罩 (用于手机/竖屏平板点选收合) */
        #sidebar-backdrop {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.6);
            backdrop-filter: blur(5px);
            z-index: 1040;
            transition: opacity 0.3s;
        }

        /* 放大 5% 的高質感卡片 */
        .stat-card, .panel-card { 
            background: var(--apple-card); 
            backdrop-filter: blur(25px);
            border: 1px solid var(--apple-border); 
            border-radius: 24px; 
            padding: 30px; /* 放大 5% */
            box-shadow: 0 20px 42px rgba(0,0,0,0.45); 
            height: 100%; 
        }
        .stat-title { font-size: 13.8px; font-weight: 600; color: #86868b; text-transform: uppercase; margin-bottom: 11px; }
        .stat-value { font-size: 32px; font-weight: 700; color: #ffffff; word-break: break-all; }
        .panel-header { font-weight: 600; color: #ffffff; font-size: 18px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }

        .console-box { 
            background-color: rgba(0, 0, 0, 0.75); color: #34d399; font-family: "SF Mono", Consolas, monospace; 
            height: 460px; overflow-y: auto; padding: 22px; border-radius: 15px; font-size: 14.2px; line-height: 1.7; border: 1px solid var(--apple-border); 
        }
        
        .guild-row { 
            background: rgba(255, 255, 255, 0.025); border: 1px solid var(--apple-border); border-radius: 17px; 
            padding: 20px 26px; margin-bottom: 17px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; 
        }

        .setting-row { display: flex; align-items: center; gap: 20px; margin-bottom: 26px; }
        .setting-row .form-check-input { width: 3.6em !important; height: 1.9em !important; cursor: pointer; background-color: rgba(255,255,255,0.1); border-color: var(--apple-border); }
        .setting-row .form-check-input:checked { background-color: var(--apple-blue); border-color: var(--apple-blue); }
        .setting-row label { margin: 0 !important; font-size: 17px !important; color: #f5f5f7; font-weight: 500; cursor: pointer; }

        .tab-pane { display: none; }
        .tab-pane.active { display: block; animation: appleFadeIn 0.6s var(--apple-ease) forwards; }
        @keyframes appleFadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

        /* 📱 完美兼容跨螢幕（橫直屏手機、平板、小筆電） */
        @media (max-width: 1024px) {
            .sidebar { transform: translateX(-285px); }
            .sidebar.show { transform: translateX(0); }
            .main-content { margin-left: 0 !important; padding: 24px; }
            .mobile-header { display: flex; }
        }
        
        @media (max-width: 576px) {
            .main-content { padding: 16px; }
            .stat-card, .panel-card { padding: 22px; }
            .stat-value { font-size: 26px; }
            .guild-row { flex-direction: column; align-items: flex-start; }
            .guild-row .d-flex { width: 100%; justify-content: space-between; margin-top: 10px; }
        }
    </style>
</head>
<body>

<!-- 移动端侧边栏点击背景自动收起遮罩 -->
<div id="sidebar-backdrop" onclick="toggleSidebar()"></div>

<!-- 苹果风动态离线等待遮罩 -->
<div id="offline-overlay">
    <div class="offline-card">
        <div class="spinner-border text-primary mb-3" style="width: 3.2rem; height: 3.2rem;" role="status"></div>
        <h4 class="fw-bold text-white mb-2">等待 Bot 核心连线中...</h4>
        <p class="text-secondary small mb-3">网页控制台常驻中，请启动 `bot.py` 程序以解锁完整仪表板。</p>
        <span class="badge bg-danger bg-opacity-25 text-danger px-3 py-2 rounded-pill">
            <i class="fa-solid fa-triangle-exclamation me-1"></i> 核心未运行 (Offline)
        </span>
    </div>
</div>

<div class="sidebar" id="sidebar">
    <div class="sidebar-brand">
        <i class="fa-solid fa-cube text-primary"></i> Novis ui
    </div>
    <ul class="sidebar-menu mt-3">
        <li><a class="active" onclick="switchTab('dashboard', this)"><i class="fa-solid fa-chart-pie"></i> 仪表板中心</a></li>
        <li><a onclick="switchTab('servers', this)"><i class="fa-solid fa-server"></i> 服务器管理</a></li>
        <li><a onclick="switchTab('settings', this)"><i class="fa-solid fa-sliders"></i> 功能开关设定</a></li>
        <li><a onclick="switchTab('console', this)"><i class="fa-solid fa-terminal"></i> 系统运行日志</a></li>
    </ul>
</div>

<div class="main-content">
    
    <!-- 移动端 / 平板专属顶部选单列 -->
    <div class="mobile-header">
        <div class="d-flex align-items-center gap-3">
            <button class="btn btn-dark text-primary border border-secondary px-3 py-2" onclick="toggleSidebar()"><i class="fa-solid fa-bars fa-lg"></i></button>
            <span class="fw-bold text-white fs-5">Novis ui 控制台</span>
        </div>
        <span class="badge bg-success bg-opacity-25 text-success px-2 py-1">运行中</span>
    </div>

    <div class="top-bar d-none d-lg-flex">
        <div>
            <h2 class="fw-bold text-white mb-1" style="font-size: 30px;"><i class="fa-solid fa-gauge-high text-primary me-2"></i>Novis ui 独立控制台</h2>
            <p class="text-secondary mb-0">网页服务常驻中，跨终端全平台完美自适应。</p>
        </div>
        <div>
            <span class="badge bg-success bg-opacity-25 text-success px-4 py-2 fw-bold border border-success border-opacity-50 rounded-pill" style="font-size: 14.5px;">
                <i class="fa-solid fa-circle-check me-1"></i> 网页服务常驻中
            </span>
        </div>
    </div>

    <!-- 分页 1 -->
    <div id="tab-dashboard" class="tab-pane active">
        <div class="row g-4 mb-4">
            <div class="col-xl-3 col-md-6 col-12">
                <div class="stat-card">
                    <div class="stat-title">已连线服务器</div>
                    <div class="stat-value text-white" id="stat-servers-count">0</div>
                </div>
            </div>
            <div class="col-xl-3 col-md-6 col-12">
                <div class="stat-card">
                    <div class="stat-title">累计下载总容量</div>
                    <div class="stat-value text-success" id="stat-total-size">0.00 MB</div>
                </div>
            </div>
            <div class="col-xl-3 col-md-6 col-12">
                <div class="stat-card">
                    <div class="stat-title">已完成任务总数</div>
                    <div class="stat-value text-info" id="stat-task-count">0</div>
                </div>
            </div>
            <div class="col-xl-3 col-md-6 col-12">
                <div class="stat-card">
                    <div class="stat-title">云端托管状态</div>
                    <div class="stat-value text-warning" style="font-size: 24px;">GitHub API</div>
                </div>
            </div>
        </div>

        <div class="panel-card p-4">
            <div class="panel-header mb-3">
                <span><i class="fa-solid fa-tasks text-info me-2"></i>即时任务处理进度与状态</span>
            </div>
            <div class="d-flex justify-content-between mb-2">
                <span id="status-text" class="fw-bold text-warning">系统闲置中...</span>
                <span id="progress-percent" class="fw-bold text-white">0%</span>
            </div>
            <div class="progress" style="height: 18px; background-color: rgba(255,255,255,0.05); border-radius: 980px;">
                <div id="progress-bar" class="progress-bar bg-primary" role="progressbar" style="width: 0%; border-radius: 980px;">0%</div>
            </div>
        </div>

        <div class="row g-4 mt-2">
            <div class="col-lg-6 col-12">
                <div class="panel-card">
                    <div class="panel-header"><span><i class="fa-solid fa-chart-line text-success me-2"></i>CPU 与系统活动曲线</span></div>
                    <div style="height: 280px;"><canvas id="cpuChart"></canvas></div>
                </div>
            </div>
            <div class="col-lg-6 col-12">
                <div class="panel-card">
                    <div class="panel-header"><span><i class="fa-solid fa-chart-area text-info me-2"></i>下载流量趋势 (MB)</span></div>
                    <div style="height: 280px;"><canvas id="memoryChart"></canvas></div>
                </div>
            </div>
        </div>
    </div>

    <!-- 分页 2：服务器管理 -->
    <div id="tab-servers" class="tab-pane">
        <div class="panel-card">
            <div class="panel-header"><span><i class="fa-solid fa-server text-success me-2"></i>已加入的 Discord 服务器管理</span></div>
            <div class="p-3" id="guild-list">
                <div class="text-center text-secondary py-4">正在载入服务器资料...</div>
            </div>
        </div>
    </div>

    <!-- 分页 3：功能开关设定 -->
    <div id="tab-settings" class="tab-pane">
        <div class="panel-card">
            <div class="panel-header"><span><i class="fa-solid fa-sliders text-warning me-2"></i>动态功能开关控制面板</span></div>
            <div class="p-4">
                <div class="setting-row">
                    <input class="form-check-input" type="checkbox" id="biliToggle" onchange="updateSettings()">
                    <label for="biliToggle">允许 Bilibili 影音下载 (1080p Cookie 支持)</label>
                </div>
                <div class="setting-row">
                    <input class="form-check-input" type="checkbox" id="ytToggle" onchange="updateSettings()">
                    <label for="ytToggle">允许 YouTube 影音下载</label>
                </div>
                <div class="setting-row">
                    <input class="form-check-input" type="checkbox" id="tkToggle" onchange="updateSettings()">
                    <label for="tkToggle">允许 TikTok 影音下载</label>
                </div>
                <div class="setting-row">
                    <input class="form-check-input" type="checkbox" id="uploadToggle" onchange="updateSettings()">
                    <label for="uploadToggle">自动上传档案至 GitHub 云端 Release</label>
                </div>
            </div>
        </div>
    </div>

    <!-- 分页 4：日志 -->
    <div id="tab-console" class="tab-pane">
        <div class="panel-card">
            <div class="panel-header">
                <span><i class="fa-solid fa-terminal text-info me-2"></i>系统运行即时日志</span>
                <button class="btn btn-sm btn-outline-danger px-3 py-2 rounded-pill" onclick="clearLogs()"><i class="fa-solid fa-trash me-1"></i> 清空</button>
            </div>
            <div class="p-2">
                <div class="console-box" id="log-box">等待系统日志输出...</div>
            </div>
        </div>
    </div>
</div>

<script>
let cpuCtx = document.getElementById('cpuChart').getContext('2d');
let cpuChart = new Chart(cpuCtx, {
    type: 'line',
    data: {
        labels: ['10分钟前', '8分钟前', '6分钟前', '4分钟前', '2分钟前', '刚刚'],
        datasets: [{ label: 'CPU 负载 (%)', data: [2.1, 1.8, 3.2, 2.5, 4.1, 2.3], borderColor: '#32d74b', backgroundColor: 'rgba(50, 215, 75, 0.1)', borderWidth: 3, fill: true, tension: 0.4 }]
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { grid: { color: 'rgba(255,255,255,0.05)' } }, x: { grid: { display: false } } } }
});

let memoryCtx = document.getElementById('memoryChart').getContext('2d');
let memoryChart = new Chart(memoryCtx, {
    type: 'line',
    data: {
        labels: ['10分钟前', '8分钟前', '6分鐘前', '4分钟前', '2分鐘前', '剛剛'],
        datasets: [{ label: '下载流量 (MB)', data: [0, 15, 30, 45, 60, 85], borderColor: '#0a84ff', backgroundColor: 'rgba(10, 132, 255, 0.1)', borderWidth: 3, fill: true, tension: 0.4 }]
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { grid: { color: 'rgba(255,255,255,0.05)' } }, x: { grid: { display: false } } } }
});

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    sidebar.classList.toggle('show');
    if (sidebar.classList.contains('show')) {
        backdrop.style.display = 'block';
    } else {
        backdrop.style.display = 'none';
    }
}

function switchTab(tabId, element) {
    document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.sidebar-menu a').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + tabId).classList.add('active');
    element.classList.add('active');
    
    // 在移动端或小屏幕平板切换分页面时自动收起侧边栏
    if (window.innerWidth <= 1024) {
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');
        sidebar.classList.remove('show');
        backdrop.style.display = 'none';
    }
}

let isOnline = false;

function fetchData() {
    fetch('/api/data')
    .then(res => res.json())
    .then(data => {
        const overlay = document.getElementById('offline-overlay');
        if (data.online) {
            if (!isOnline) {
                isOnline = true;
                overlay.style.opacity = '0';
                setTimeout(() => overlay.style.display = 'none', 500);
            }
            let task = data.task;
            document.getElementById('stat-servers-count').innerText = data.guilds.length;
            document.getElementById('stat-total-size').innerText = task.total_downloaded_mb >= 1024 ? 
                (task.total_downloaded_mb / 1024).toFixed(2) + ' GB' : 
                task.total_downloaded_mb.toFixed(2) + ' MB';
            document.getElementById('stat-task-count').innerText = task.download_count;

            document.getElementById('status-text').innerText = task.message;
            document.getElementById('progress-percent').innerText = task.progress + '%';
            let bar = document.getElementById('progress-bar');
            bar.style.width = task.progress + '%';
            bar.innerText = task.progress + '%';

            let guildHtml = '';
            if (data.guilds.length === 0) {
                guildHtml = '<div class="text-center text-secondary py-4">机器人目前尚未加入任何服务器</div>';
            } else {
                data.guilds.forEach(g => {
                    let isChecked = g.disabled ? '' : 'checked';
                    let statusBadge = g.disabled ? '<span class="badge bg-danger ms-2 rounded-pill">已关闭</span>' : '<span class="badge bg-success ms-2 rounded-pill">运行中</span>';
                    guildHtml += `<div class="guild-row">
                        <div>
                            <h6 class="mb-1 fw-bold text-white fs-6">${g.name} ${statusBadge}</h6>
                            <small class="text-secondary">成员数: ${g.count} | ID: ${g.id}</small>
                        </div>
                        <div class="d-flex align-items-center gap-3">
                            <div class="form-check form-switch m-0">
                                <input class="form-check-input" type="checkbox" ${isChecked} onchange="toggleGuild('${g.id}', this.checked)">
                            </div>
                            <button class="btn btn-outline-danger btn-sm rounded-pill px-3 py-2" onclick="leaveGuild('${g.id}')"><i class="fa-solid fa-right-from-bracket me-1"></i> 退出</button>
                        </div>
                    </div>`;
                });
            }
            document.getElementById('guild-list').innerHTML = guildHtml;

            document.getElementById('biliToggle').checked = data.settings.allow_bilibili;
            document.getElementById('ytToggle').checked = data.settings.allow_youtube;
            document.getElementById('tkToggle').checked = data.settings.allow_tiktok;
            document.getElementById('uploadToggle').checked = data.settings.auto_upload;

            let logBox = document.getElementById('log-box');
            let isAtBottom = logBox.scrollHeight - logBox.scrollTop <= logBox.clientHeight + 50;
            logBox.innerText = data.logs.join('');
            if (isAtBottom) { logBox.scrollTop = logBox.scrollHeight; }
        } else {
            if (isOnline) {
                isOnline = false;
                overlay.style.display = 'flex';
                setTimeout(() => overlay.style.opacity = '1', 10);
            }
        }
    })
    .catch(() => {
        isOnline = false;
        document.getElementById('offline-overlay').style.display = 'flex';
    });
}

function toggleGuild(guildId, enabled) {
    fetch('/api/toggle-guild', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({guild_id: String(guildId), enabled: enabled})
    });
}

function leaveGuild(guildId) {
    if (confirm('⚠️ 确定要让机器人退出该服务器吗？')) {
        fetch('/api/leave', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({guild_id: String(guildId)})
        });
    }
}

function updateSettings() {
    let settings = {
        allow_bilibili: document.getElementById('biliToggle').checked,
        allow_youtube: document.getElementById('ytToggle').checked,
        allow_tiktok: document.getElementById('tkToggle').checked,
        auto_upload: document.getElementById('uploadToggle').checked
    };
    fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(settings)
    });
}

function clearLogs() {
    fetch('/api/clear-logs', {method: 'POST'});
}

setInterval(fetchData, 1000);
window.onload = fetchData;
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(STANDALONE_UI_HTML)

@app.route('/api/data')
def api_data():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if time.time() - data.get("timestamp", 0) < 5:
                    return jsonify({"online": True, **data})
        except:
            pass
    return jsonify({"online": False})

@app.route('/api/toggle-guild', methods=['POST'])
def api_toggle_guild():
    data = request.json
    cmd = {"action": "toggle_guild", "guild_id": data.get("guild_id"), "enabled": data.get("enabled")}
    with open(COMMAND_FILE, "w", encoding="utf-8") as f:
        json.dump(cmd, f)
    return jsonify({"success": True})

@app.route('/api/leave', methods=['POST'])
def api_leave():
    data = request.json
    cmd = {"action": "leave_guild", "guild_id": data.get("guild_id")}
    with open(COMMAND_FILE, "w", encoding="utf-8") as f:
        json.dump(cmd, f)
    return jsonify({"success": True})

@app.route('/api/settings', methods=['POST'])
def api_settings():
    data = request.json
    cmd = {"action": "update_settings", "settings": data}
    with open(COMMAND_FILE, "w", encoding="utf-8") as f:
        json.dump(cmd, f)
    return jsonify({"success": True})

@app.route('/api/clear-logs', methods=['POST'])
def api_clear_logs():
    cmd = {"action": "clear_logs"}
    with open(COMMAND_FILE, "w", encoding="utf-8") as f:
        json.dump(cmd, f)
    return jsonify({"success": True})

import subprocess
import os
import time
import threading

def start_bot_in_background():
    """在独立线程中持续守护 bot.py，遭遇 429 限流时自动延长冷却时间"""
    def run_bot():
        current_dir = os.path.dirname(os.path.abspath(__file__))
        bot_script = os.path.join(current_dir, "bot.py")
        
        while True:
            try:
                print("🚀 [Bot Guard] 正在启动 bot.py 进程...")
                process = subprocess.Popen(["python", bot_script], env=os.environ.copy())
                process.wait()
                print("⚠️ [Bot Guard] bot.py 已退出，将在 60 秒后重新尝试启动...")
            except Exception as e:
                print(f"❌ [Bot Guard] 启动 bot.py 异常: {e}")
            
            # 将冷却时间拉长至 60 秒，避免触发 Discord 429 全球速率限制
            time.sleep(60)

    guard_thread = threading.Thread(target=run_bot, daemon=True)
    guard_thread.start()

if __name__ == "__main__":
    start_bot_in_background()
    print("🌐 独立 Novis UI 完整控制台已启动：http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
