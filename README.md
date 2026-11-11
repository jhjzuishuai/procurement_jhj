# 采购文档智能生成系统 v2（Python 版）

> 把旧版 Node.js/Express 的「采购文件智能生成系统」用 Python 技术栈重做一遍。
> 功能链路一样：**登录 → 录入需求 → 解析参数 → 匹配品类 → 生成文档 → 风险预审 → 导出 Word**。
>
> 作者：贾皓杰（JHJ）

---

## 一、这个项目做了什么

| 环节 | 说明 |
|---|---|
| 登录 | 账号密码登录，密码用 PBKDF2 加盐存储；连错 5 次锁 10 分钟；token 存数据库，重启不丢 |
| 录入需求 | 填项目名称 + 一段自由文字（预算、数量、交付期、CPU/内存/硬盘/质保都写在里面就行） |
| 解析参数 | 先用正则捞固定格式的信息，再让大模型补漏；**没配 API Key 就纯本地规则，照样跑** |
| 匹配品类 | 按品类关键词命中数量自动判断是"服务器 / 办公电脑 / 软件服务"，也支持手动指定 |
| 生成文档 | 一次生成 5 个章节：技术规格书、招标公告、招标文件主体、合同主要条款、评审标准 |
| 风险预审 | 规则检查（无预算、单价过低、无交付期、资质不足、技术参数太笼统、正文太短）+ 大模型复核 |
| 导出 Word | 用 `python-docx` 把 5 个章节排成一份 .docx |
| 版本管理 | 每次调整章节都留一条历史，可以回滚 |
| 批量 Excel | 用 `pandas` 读表格批量生成，也能把记录导成 Excel |
| 审计日志 | 登录、生成、调整、回滚、导入都记一条，管理员可查（分页） |

---

## 二、目录结构

```
procurement_jhj/
├── app/
│   ├── __init__.py          包说明
│   ├── config.py            读 .env，拼数据库连接串，建目录
│   ├── database.py          异步引擎 / 会话 / 建表 / 演示数据
│   ├── models.py            5 张表
│   ├── schemas.py           请求参数校验（Pydantic）
│   ├── security.py          密码加盐、token 生成（只用了标准库）
│   ├── deps.py              登录校验 + 角色权限
│   ├── common.py            统一返回格式、生成编号、写审计
│   ├── services/
│   │   ├── ai_service.py        调大模型（httpx）+ 清洗 JSON
│   │   ├── parse_service.py     需求解析 + 风险规则
│   │   ├── document_service.py  生成 5 个章节 + 导出 Word
│   │   └── excel_service.py     Pandas 读表 / 写表
│   └── routers/
│       ├── auth.py          注册 / 登录 / 查自己 / 退出
│       ├── categories.py    品类列表 / 新建 / 模板上传
│       ├── records.py       生成 / 列表 / 详情 / 调整 / 重生成 / 预审 / 下载 / 版本 / Excel
│       └── admin.py         审计日志 / 用户列表 / 统计
├── data/                    运行后自动生成：app.db、templates、exports
├── docs/
│   ├── 接口清单.md           每个接口的入参出参
│   └── 人工测试步骤.md        17 组 34 步手工验收步骤（无前端，在 Swagger 里测）
├── tests/test_api.py        接口自测脚本（自动跑一遍主流程）
├── requirements.txt
├── .env / .env.example      配置
├── .gitignore
├── run.ps1                  一键启动
└── run_server.py            PyCharm 里直接点绿三角运行
```

---

## 三、快速开始

### 方式一：一键脚本（推荐）

在项目根目录打开 PowerShell：

```powershell
.\run.ps1
```

脚本会自动：建虚拟环境 → 装依赖 → 复制 .env → 启动服务。

### 方式二：手动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 方式三：PyCharm

1. `File → Open`，选项目根目录 `procurement_jhj`（注意选文件夹，不要选到 `app`）
2. `Settings → Project → Python Interpreter → Add Interpreter → Add Local Interpreter`
   → 选 `Select existing`，指向 `.venv\Scripts\python.exe`
3. 右键 `run_server.py` → `Run 'run_server'`，浏览器打开 <http://127.0.0.1:8000/docs>

启动后：

- **前端页面（带块级编辑）**：<http://127.0.0.1:8000/>
  登录 → 填需求 → 生成 → 切 5 个章节 tab → 点「编辑这块」改某一段/某个表格单元格 → 导出 Word
- 接口文档（可以直接点着测）：<http://127.0.0.1:8000/docs>
  **右上角有 Authorize 按钮**：先调 `POST /api/auth/login` 拿 token，点 Authorize 填进去，后面所有接口自动带凭证
- 健康检查：<http://127.0.0.1:8000/api/health>

### 演示账号

| 账号 | 密码 | 角色 | 能干什么 |
|---|---|---|---|
| admin | Jhj@123456 | 管理员 | 全部功能（含品类模板、审计日志） |
| buyer | Buyer@123 | 采购员 | 生成文件、查记录、导出 |
| expert | Expert@123 | 采购专家 | 生成文件 + 风险复核 + 调整章节 |

### 跑测试

**方式一：pytest（推荐，27 项，约 10 秒）**

```powershell
.\.venv\Scripts\pip.exe install -r requirements-dev.txt   # 首次需要装 pytest
.\.venv\Scripts\python.exe -m pytest
```

想看得更细：`-v` 每项一行，`--durations=8` 看哪几项最慢，`-x` 第一个失败就停。

测试有三个刻意的设计：

- **不碰演示库**：`tests/conftest.py` 在 `import app` 之前把 `DATABASE_URL` 指到 `data/test.db`
- **不调真实大模型**：同一处把 `AI_API_KEY` 置空，走本地规则，结果可复现、不花钱、不受网络影响
- **建表只做一次**：会话开始建表 + 写演示数据，每个测试之间只清业务数据

覆盖：前端首页与静态资源、登录、当前用户、未登录 401、越权 403、退出后 token 失效、生成、参数识别（预算/数量/交付期/品类）、列表、详情、下载 Word、调整、版本、回滚、块级编辑（改/插/删 + 5 种非法输入）、重新预审、导出 Excel、批量导入、品类、审计日志。

**方式二：老的冒烟脚本（30 项，print 风格，会写真实库）**

```powershell
.\.venv\Scripts\python.exe tests\test_api.py
```

它按真实使用顺序走一遍、结果打印在屏幕上，适合"我只想快速确认服务还活着"。注意它用的是 `data\app.db`，会真的往演示库里加记录。

### 手工测试（有前端页面，也可以走 Swagger）

前端：<http://127.0.0.1:8000/>（登录 → 生成 → 切章节 → 块级编辑 → 导出）
Swagger：<http://127.0.0.1:8000/docs>

看 `docs\人工测试步骤.md`，17 组 34 步，每步都写清了"点哪个按钮、填什么、应该看到什么"。

测试素材已经放好：

| 文件 | 用途 |
|---|---|
| `data\templates\示例模板_服务器技术规格书.docx` | 测上传模板，里面有 7 个 `{{占位符}}` |
| `data\exports\需求导入示例.xlsx` | 测批量导入，3 行需求 |

想从零重来一遍：停掉服务，删掉 `data\app.db`，再启动即可（会自动重建 3 个账号和 3 个品类，记录数为 0）。

---

## 四、换 MySQL 怎么弄

1. 先在 Navicat 或命令行建库（SQLAlchemy 只建表，不建库）：

```sql
CREATE DATABASE procurement_jhj DEFAULT CHARACTER SET utf8mb4;
```

2. 改 `.env`：

```ini
DATABASE_URL=mysql+aiomysql://root:Jhj%40123456@127.0.0.1:3306/procurement_jhj?charset=utf8mb4
```

3. 重新启动服务，`create_all()` 会自动建表、写入演示数据。

> 注意：密码里的 `@` 必须写成 `%40`，否则连接串会在 `@` 处被截断。

---

## 五、接口清单（共 23 个）

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /api/health | 健康检查（不登录也能看） | - |
| POST | /api/auth/register | 注册（默认 buyer） | - |
| POST | /api/auth/login | 登录，返回 token | - |
| GET | /api/auth/me | 当前登录用户 | 已登录 |
| POST | /api/auth/logout | 退出 | 已登录 |
| GET | /api/categories | 品类列表 | 已登录 |
| POST | /api/categories | 新建品类 | admin |
| POST | /api/categories/{code}/template | 上传 Word 模板，自动识别 `{{占位符}}` | admin |
| DELETE | /api/categories/{code}/template | 删除模板 | admin |
| POST | /api/records/generate | 录入需求生成文件（核心接口） | admin/buyer/expert |
| GET | /api/records | 记录列表（分页 + 关键字） | 已登录 |
| GET | /api/records/{id} | 记录详情（含参数、5 章节、风险） | 已登录 |
| POST | /api/records/{id}/adjust | 调整某个章节，自动记版本 | expert/admin |
| PATCH | /api/records/{id}/document | **块级编辑**：改/增/删某一章里的某一块 | expert/admin |
| POST | /api/records/{id}/regenerate | 按原需求重新生成 | admin/buyer/expert |
| POST | /api/records/{id}/review-risks | 重新风险预审 | expert/admin |
| GET | /api/records/{id}/download | 下载 Word | 已登录 |
| GET | /api/records/{id}/versions | 修改历史 | 已登录 |
| POST | /api/records/{id}/versions/{index}/restore | 回滚 | expert/admin |
| POST | /api/records/import-excel | 批量导入需求 | admin/buyer/expert |
| GET | /api/records/export-excel | 导出记录清单 | 已登录 |
| GET | /api/admin/audit-logs | 审计日志（分页） | admin |
| GET | /api/admin/users | 用户列表 | admin |
| GET | /api/admin/stats | 统计 | admin |

详细入参出参见 `docs/接口清单.md`。

---

## 六、设计上刻意做的几件事（和旧版对比）

| 旧版（Node 版）的问题 | 这里怎么处理 |
|---|---|
| 整个数据库 `JSON.stringify` 塞进一张 `app_state` 表，每个请求全量读写 | 拆成 5 张真正的表，有主键、有唯一索引，走 SQL 查询 |
| 单文件 2389 行 | 按 配置 / 模型 / 安全 / 依赖 / 服务 / 路由 分层 |
| 密码裸 `sha256` | `pbkdf2_hmac + 随机盐 + compare_digest` |
| 登录状态放内存 Map，重启就掉 | token 存 `user_session` 表，带过期时间 |
| AI 调用逻辑复制了 4 份 | 统一收在 `ai_service.call_ai()` 一个函数里 |
| 大模型挂了接口就报错 | 任何异常都返回 `None`，自动降级本地规则 |
| 中文乱码，还要靠 4 个启发式函数修补 | 连接串统一 `utf8mb4`，代码文件全部 UTF-8 |
| 记录列表无分页，每条内嵌 5 份完整 HTML | 加了分页和关键字搜索；列表目前仍复用详情结构（sections 全量返回，瘦身待做） |

另外特意按「基础函数」写，**没有**用 LangChain、向量库、ABC 抽象基类、泛型魔法：

- 解析就是 `re.search` + `if` 判断 + 列表拼接
- 章节生成就是拼字典、拼列表
- 导出 Word 就是 `python-docx` 一段一段 `add_paragraph`
- Excel 就是 `pd.read_excel` / `df.to_excel`
- 大模型就是 `httpx.AsyncClient().post()`，和 `requests.post()` 一个思路，只是加了 `await`

---

## 七、已知限制（自己心里要有数）

1. **前端只有单页**：登录、生成、看 5 章节、块级编辑、记录列表、下载。模板库和管理后台还没做页面，仍走 Swagger。
2. **模板上传只做占位符识别**，还没有"按模板真填值"的动作（要做的话用 `docxtpl` 渲染 `{{字段}}`，属于下一版）。
3. **批量导入为了速度只走本地规则**，不逐条调大模型（50 条 × 30 秒会把接口拖死）。
4. **文档的 5 个章节是模板化生成的**，接入大模型后可以把正文写得更专业，结构不变。
5. **单机单进程**够用；上生产要换 MySQL + 多 worker + 把 token 换 JWT。

---

## 八、可以继续做的事

- [ ] 用 `docxtpl` 把上传的 Word 模板真正渲染出来
- [x] 加一个原生 HTML 单页界面（`static/`，已支持块级编辑）
- [ ] 给前端补模板库 / 管理后台两个视图（旧版 `frontend/` 可参考）
- [ ] 用 APScheduler 做定时清理过期 token
- [ ] 给 `records` 加 `category_code` 独立列 + 索引，品类统计就不用扫 JSON
- [ ] 用 `pytest` 重写 `tests/`，加单测覆盖解析规则

---

## 九、PyCharm 常见报错怎么处理

| 报错 | 原因 | 处理 |
|---|---|---|
| 满屏 **"未解析的引用 'fastapi' / 'APIRouter'"**，但程序能跑 | PyCharm 缓存的解释器路径没包含 `.venv\Lib\site-packages` | 删除旧解释器重新加一次，再 `File → Invalidate Caches` 清缓存（见下方"解释器自检"） |
| `ModuleNotFoundError: No module named 'app'` | 运行配置的 Working directory 指到了 `app` 目录 | `Run → Edit Configurations`，Working directory 改回项目根目录 |
| `ModuleNotFoundError: No module named 'fastapi'` | 解释器选成了系统 Python，不是 `.venv` | `Settings → Python Interpreter` 换成 `.venv\Scripts\python.exe` |
| `无法加载文件 ...Activate.ps1，因为在此系统上禁止运行脚本` | PowerShell 执行策略限制 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，或者干脆不激活，直接用 `run_server.py` 运行 |
| `[Errno 10048] 只能有一个使用以下地址的套接字` / `address already in use` | 8000 端口被上一次没关掉的服务占着 | 关掉旧进程，或把 `run_server.py` 里 `port` 改成 8001 |
| 控制台中文显示成方块或乱码 | IDE 编码没设成 UTF-8 | `Settings → Editor → File Encodings`，三处都选 `UTF-8` |
| `1049, "Unknown database ..."`（换了 MySQL 才会出现） | 只建了表没建库 | 先在 Navicat 里执行 `CREATE DATABASE procurement_jhj` |

### 解释器自检（怕 venv 建歪了就查这个）

`.venv\pyvenv.cfg` 里的 `home` **必须是你本机的 Python 目录**，例如：

```
home = D:\PYTHON
version = 3.13.12
```

如果 `home` 指向什么 `sandbox_runtime`、`Temp`、`JetBrains\...` 之类的临时目录，说明这个 venv 是某个临时运行时建的，PyCharm 索引不到里面的包，而且那个目录被清掉后项目直接跑不起来。处理办法是删掉 `.venv`，用本机 Python 重来：

```powershell
Remove-Item -LiteralPath ".venv" -Recurse -Force
D:\PYTHON\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 满屏"未解析的引用"的修法

这是 PyCharm 的索引没吃到 `.venv\Lib\site-packages`，代码本身没问题（能跑、能过测试就说明包是好的）。

1. `Ctrl+Alt+S` 打开 Settings → `Project: procurement_jhj` → `Python Interpreter`
2. 点右上齿轮 → `Show All...` → 选中 `Python 3.13 (procurement_jhj)` → 点 **减号**删掉它
3. 回到解释器页 → `Add Interpreter` → `Add Local Interpreter` → 左边选 `Virtualenv Environment` → 勾 **`Existing`**（不要选 New）
4. `Interpreter` 填 `D:\生产实习\Project_7_5(6)\procurement_jhj\.venv\Scripts\python.exe` → `OK`
5. `File → Invalidate Caches...` → 勾上 `Clear file system cache and Local History` → `Invalidate and Restart`
6. 重启后等右下角索引进度条走完，红线就消失了


不是 PyCharm 的锅但经常一起出现的：**本机没装 Git** 的话，`git init` 会报"不是内部或外部命令"，装个 Git 再建仓库。
