# Python Web 应用开发避坑指南

当用户要求开发 Web 应用、网页版产品、给同事用的内部工具时，使用此 Skill。

## 触发场景
- "做成网页版"
- "封装成产品"
- "让同事也能用"
- "做个 Web 界面"
- 任何涉及 Python HTTP Server + 前端的开发任务

---

## 🚨 核心铁律（违反必翻车）

### 1. 前端框架 CDN 在国内不可靠

**问题**：Vue、React、Element Plus 等 CDN 在国内网络环境下经常加载失败，导致页面白屏。

**解决方案**：
- ✅ **纯原生 JS 优先**：内部工具不需要框架，原生 JS + CSS 完全够用
- ✅ 如果必须用框架，**内嵌 JS 文件**而非引用 CDN
- ✅ CDN 只用于非关键资源（如图表库 ECharts），加载失败不影响核心功能
- ❌ 绝不依赖 Vue + Element Plus + Icons 三个 CDN 同时加载成功

**反面案例**：本次开发中，Element Plus Icons CDN 加载失败导致整个 Vue 应用崩溃白屏，换了纯原生 JS 才解决。

### 2. 服务重启 = Session 全部失效

**问题**：Python HTTPServer 的内存 session 在进程重启后全部清空，但用户浏览器 localStorage 里还存着旧 token。页面以为已登录，API 返回 401，结果什么都不渲染——白屏。

**解决方案**：
```javascript
// API 层统一处理 401
xhr.onload = function () {
  if (xhr.status === 401) {
    // 清除本地 token，回到登录页
    localStorage.removeItem('token');
    renderLogin();
    return;
  }
  // 正常处理...
};
```

**关键原则**：任何需要认证的 API 调用，都必须处理 401 响应，**绝不假设 token 永远有效**。

### 3. 数据库 Schema 和代码必须同步

**问题**：代码中 INSERT 了一个数据库表不存在的列（如 `uploaded_by`），导致 `OperationalError`。

**解决方案**：
- ✅ **Schema 变更写进初始化脚本**（`ensure_tables()` 中用 `ALTER TABLE ADD COLUMN IF NOT EXISTS`）
- ✅ 启动时自动检查并补全缺失的列
- ❌ 绝不手动 `ALTER TABLE` 后忘记更新代码

```python
def ensure_tables():
    conn = get_db()
    # 安全地添加新列（忽略已存在的）
    for col_sql in [
        "ALTER TABLE task_queue ADD COLUMN uploaded_by TEXT",
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass  # 列已存在，忽略
    conn.commit()
    conn.close()
```

### 4. 不要继承 SimpleHTTPRequestHandler 的 do_GET

**问题**：继承 `SimpleHTTPRequestHandler` 并在 `do_GET` 中调用 `super().do_GET()` 处理静态文件时，某些路径会阻塞或 404。

**解决方案**：
```python
def do_GET(self):
    path, params = self._parse_url()
    # 只处理已知路由
    if path in routes:
        routes[path](params)
    elif path == "/" or path == "/index.html":
        self._serve_html()
    else:
        # 直接返回 404，不调用 super().do_GET()
        self._send_json({"error": "Not found"}, 404)
```

### 5. Element Plus el-radio 的 label vs value

**问题**：Element Plus 2.6+ 中 `el-radio` 用 `label` 属性绑定值，而非常见框架的 `value`。用 `value` 的话单选按钮不响应。

**解决方案**：
```html
<!-- ❌ 错误 -->
<el-radio value="auto">自动</el-radio>

<!-- ✅ 正确 -->
<el-radio label="auto">自动</el-radio>
```

### 6. cgi.FieldStorage 上传文件

**问题**：Python 标准库 `cgi.FieldStorage` 用于解析 multipart/form-data，但在某些 Python 版本中行为不一致。

**解决方案**：
- ✅ 对于简单上传，使用 `cgi.FieldStorage` 但包裹 try/except
- ✅ 记录每个文件的 filename，判断是否真的有文件上传
- ✅ 注意 `form["files"]` 在单文件和多文件时返回类型不同（单文件直接是 Field，多文件是 list）

```python
form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={...})
files = form["files"]
if not isinstance(files, list):
    files = [files]
for f in files:
    if not f.filename:
        continue  # 跳过空文件
```

### 7. HTTPServer 后台进程管理

**问题**：`python3 server.py &` 在 exec 中会随会话结束而退出。需要用 `nohup` 或 OpenClaw 的 background 模式。

**解决方案**：
```bash
# 推荐：nohup + 后台
nohup python3 server.py > /tmp/app.log 2>&1 &

# OpenClaw 中：
exec background=true, command="nohup python3 server.py > /tmp/app.log 2>&1 &"
```

### 8. SQLite 并发写入

**问题**：SQLite 不支持并发写入，多线程同时 INSERT/UPDATE 会锁表。

**解决方案**：
```python
# 启用 WAL 模式（允许读写并发）
conn.execute("PRAGMA journal_mode=WAL")
```

---

## ✅ 推荐的项目结构

```
my-web-app/
├── server.py          # 单文件后端（零依赖，标准库即可）
├── index.html         # 单文件前端（原生 JS，可选 ECharts CDN）
└── data/
    └── app.db         # SQLite 数据库
```

**为什么单文件？**
- 内部工具不需要微服务架构
- 部署简单：一个 `python3 server.py` 搞定
- 同事用起来方便：复制两个文件就能跑
- 不需要 npm install / pip install / docker build

---

## ✅ 推荐的 API 设计模式

```python
class APIHandler(SimpleHTTPRequestHandler):
    def _send_json(self, data, code=200):
        """统一 JSON 响应"""
        
    def _read_json(self):
        """读取 JSON 请求体"""
        
    def _require_auth(self):
        """统一认证检查，失败返回 401"""
        
    def do_GET(self):
        """路由分发"""
        
    def do_POST(self):
        """路由分发"""
```

**关键原则**：
- 所有 API 响应统一 JSON 格式
- 认证失败返回 `{"error": "xxx"}, 401`
- 业务错误返回 `{"error": "xxx"}, 400`
- 成功返回 `{"data": ...}, 200`

---

## ✅ 推荐的前端渲染模式

```javascript
// 状态管理
var S = { token: '', page: 'dash', ... };

// 渲染函数（根据状态重绘整个页面）
function render() {
  if (!S.token) { renderLogin(); return; }
  if (S.page === 'dash') renderDash();
  if (S.page === 'list') renderList();
}

// API 调用（统一处理 401）
function api(method, url, data) {
  return new Promise(function(ok, fail) {
    var xhr = new XMLHttpRequest();
    xhr.onload = function() {
      if (xhr.status === 401) { doLogout(); return; }
      ok(JSON.parse(xhr.responseText));
    };
    // ...
  });
}
```

**关键原则**：
- 每次渲染都是完整的 innerHTML 替换（简单可靠）
- API 层统一处理 401 → 自动登出
- 不使用 SPA 框架，不使用 Virtual DOM

---

## 📋 开发自检清单

发布前必须检查：

- [ ] **CDN 降级**：核心功能不依赖任何 CDN，CDN 只用于图表等增强功能
- [ ] **401 处理**：所有 API 调用都有 401 → 自动登出逻辑
- [ ] **Schema 同步**：`ensure_tables()` 包含所有列的 ALTER TABLE
- [ ] **WAL 模式**：SQLite 开启 WAL
- [ ] **SQL 注入**：所有用户输入参数化查询，转义单引号
- [ ] **文件上传**：检查文件后缀白名单、大小限制
- [ ] **错误日志**：所有异常都记录到日志文件
- [ ] **进程管理**：使用 nohup 或 systemd 管理后台进程
- [ ] **端口冲突**：启动前检查端口是否被占用
