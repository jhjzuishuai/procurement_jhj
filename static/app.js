// -*- coding: utf-8 -*-
// 前端逻辑：原生 JS + fetch，不依赖任何框架（作者：贾皓杰 JHJ）
//
// 只做四件事：登录 / 生成 / 看章节并做「块级编辑」 / 下载 Word
// 后端接口前缀都在同一个域名下，所以 API 路径直接写相对地址。

// ---------------- 常量 ----------------

// 五个章节的 key 和后端 sections_json 的键一一对应
const SECTION_KEYS = ["techSpec", "announcement", "bid", "contract", "evaluation"];
const SECTION_LABELS = {
  techSpec: "规格书",
  announcement: "公告",
  bid: "招标文件",
  contract: "合同",
  evaluation: "评审",
};
const LEVEL_LABELS = { HIGH: "高", MEDIUM: "中", LOW: "低" };

// ---------------- 全局状态 ----------------
const state = {
  token: localStorage.getItem("jhj_token") || "",
  me: null,
  record: null,        // 当前正在编辑的记录（后端返回的完整对象）
  section: "techSpec", // 当前展示的章节
  editingIndex: -1,    // 正在编辑的块下标，-1 表示非编辑态
  records: [],
};

// ---------------- 小工具 ----------------

function $(id) {
  return document.getElementById(id);
}

function toast(text) {
  const box = $("toast");
  box.textContent = text;
  box.classList.add("show");
  setTimeout(function () {
    box.classList.remove("show");
  }, 2500);
}

// 统一请求：自动带 token，统一解析 {code,msg,data}，出错抛出可读信息
async function api(path, options) {
  options = options || {};
  const headers = Object.assign({}, options.headers || {});
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (state.token) {
    headers["Authorization"] = "Bearer " + state.token;
  }

  let response;
  try {
    response = await fetch(path, Object.assign({}, options, { headers: headers }));
  } catch (error) {
    throw new Error("无法连接后端，请确认服务已启动（python run_server.py）");
  }

  const contentType = response.headers.get("content-type") || "";
  let body = null;
  if (contentType.includes("application/json")) {
    body = await response.json();
  }

  if (!response.ok) {
    // 后端两种错误格式：统一返回 {code,msg} / FastAPI 的 {detail}
    let message = "请求失败：" + response.status;
    if (body) {
      message = body.detail || body.msg || message;
    }
    throw new Error(message);
  }
  return body;
}

function switchView(name) {
  document.querySelectorAll(".view").forEach(function (item) {
    item.classList.remove("active");
  });
  $(name + "-view").classList.add("active");
  document.querySelectorAll(".nav-item").forEach(function (item) {
    item.classList.toggle("active", item.dataset.view === name);
  });
}

// ---------------- 登录 / 退出 ----------------

function enterApp() {
  $("authScreen").hidden = true;
  $("appShell").hidden = false;
  $("currentUser").textContent = state.me ? (state.me.display_name || state.me.username) : "";
  $("currentRole").textContent = state.me ? state.me.role : "";
  loadCategories();
  loadRecords();
}

async function doLogin(event) {
  event.preventDefault();
  $("loginHint").textContent = "登录中…";
  try {
    const result = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("loginUsername").value.trim(),
        password: $("loginPassword").value,
      }),
    });
    state.token = result.data.token;
    state.me = result.data.user;
    localStorage.setItem("jhj_token", state.token);
    $("loginHint").textContent = "";
    enterApp();
    toast("登录成功");
  } catch (error) {
    $("loginHint").textContent = error.message;
  }
}

async function doLogout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (error) {
    // 退出失败也照样清本地状态
  }
  state.token = "";
  state.me = null;
  state.record = null;
  localStorage.removeItem("jhj_token");
  $("appShell").hidden = true;
  $("authScreen").hidden = false;
}

// ---------------- 品类 / 生成 ----------------

async function loadCategories() {
  try {
    const result = await api("/api/categories");
    const select = $("categorySelect");
    select.innerHTML = "";
    const auto = document.createElement("option");
    auto.value = "";
    auto.textContent = "自动识别";
    select.appendChild(auto);

    (result.data || []).forEach(function (item) {
      const option = document.createElement("option");
      option.value = item.code;
      option.textContent = item.name + "（" + item.code + "）";
      select.appendChild(option);
    });
  } catch (error) {
    toast("品类加载失败：" + error.message);
  }
}

function fillDemo() {
  $("title").value = "2026年机房服务器采购项目";
  $("content").value =
    "采购机架式服务器100台。预算为800万元。合同签订后45天内完成供货和安装调试。" +
    "CPU要求不低于32核64线程，内存不低于512GB DDR5，硬盘不低于2块960GB SSD，" +
    "网络配置双万兆网卡。质保3年，需提供培训服务和远程运维支持。";
  $("budget").value = "";
  $("delivery").value = "";
  $("supplier").value = "具备营业执照、具备同类项目经验、具备原厂授权";
}

async function doGenerate(event) {
  event.preventDefault();
  $("runState").textContent = "生成中…";
  try {
    const body = {
      title: $("title").value.trim(),
      content: $("content").value.trim(),
      budget: Number($("budget").value || 0),
      delivery: $("delivery").value.trim(),
      supplier: $("supplier").value.trim(),
      category_code: $("categorySelect").value,
    };
    const result = await api("/api/records/generate", {
      method: "POST",
      body: JSON.stringify(body),
    });
    state.record = result.data;
    state.section = "techSpec";
    state.editingIndex = -1;

    $("runState").textContent = "已生成";
    $("editState").textContent = "编号 " + state.record.generation_no;
    $("exportBtn").disabled = false;

    renderAll();
    switchView("workspace");
    toast("生成成功");
  } catch (error) {
    $("runState").textContent = "生成失败";
    toast(error.message);
  }
}

// ---------------- 渲染：参数 / 章节 / 风险 ----------------

function renderParams() {
  if (!state.record) {
    return;
  }
  $("structuredOutput").textContent = JSON.stringify(state.record.parameters, null, 2);
}

function renderTabs() {
  const box = $("sectionTabs");
  box.innerHTML = "";
  if (!state.record) {
    return;
  }
  SECTION_KEYS.forEach(function (key) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tab" + (state.section === key ? " active" : "");
    button.textContent = SECTION_LABELS[key];
    button.onclick = function () {
      state.section = key;
      state.editingIndex = -1;
      renderTabs();
      renderSection();
    };
    box.appendChild(button);
  });
}

function renderSection() {
  const box = $("documentPreview");
  box.innerHTML = "";

  if (!state.record || !state.record.sections) {
    box.innerHTML = '<p class="empty-text">暂无草案</p>';
    return;
  }

  const part = state.record.sections[state.section];
  if (!part) {
    box.innerHTML = '<p class="empty-text">该章节为空</p>';
    return;
  }

  const title = document.createElement("h4");
  title.textContent = part.title || SECTION_LABELS[state.section];
  box.appendChild(title);

  const blocks = part.blocks || [];
  blocks.forEach(function (block, index) {
    box.appendChild(state.editingIndex === index ? blockEditor(block, index) : blockView(block, index));
  });
}

// 展示态的一块
function blockView(block, index) {
  const row = document.createElement("div");
  row.className = "block-row";

  const head = document.createElement("div");
  head.className = "block-head";
  head.innerHTML =
    '<span class="block-index">#' + index + '</span><span class="block-tag">' + block.type + "</span>";
  row.appendChild(head);

  if (block.type === "p") {
    const p = document.createElement("p");
    p.textContent = block.text || "";
    row.appendChild(p);
  } else if (block.type === "list") {
    const list = document.createElement("ul");
    (block.items || []).forEach(function (item) {
      const li = document.createElement("li");
      li.textContent = item;
      list.appendChild(li);
    });
    row.appendChild(list);
  } else if (block.type === "table") {
    row.appendChild(tableElement(block.rows || [], false));
  }

  const bar = document.createElement("div");
  bar.className = "block-toolbar";

  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "secondary-button";
  editBtn.textContent = "编辑这块";
  editBtn.onclick = function () {
    state.editingIndex = index;
    renderSection();
  };

  const insertBtn = document.createElement("button");
  insertBtn.type = "button";
  insertBtn.className = "secondary-button";
  insertBtn.textContent = "在此处插入段落";
  insertBtn.onclick = function () {
    insertBlock(index);
  };

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "secondary-button";
  deleteBtn.textContent = "删除这块";
  deleteBtn.onclick = function () {
    deleteBlock(index);
  };

  bar.appendChild(editBtn);
  bar.appendChild(insertBtn);
  bar.appendChild(deleteBtn);
  row.appendChild(bar);
  return row;
}

// 表格：编辑态时每个单元格是 input
function tableElement(rows, editable) {
  const table = document.createElement("table");
  table.className = "spec-table";
  rows.forEach(function (row, rowIndex) {
    const tr = document.createElement("tr");
    row.forEach(function (cell, cellIndex) {
      const td = document.createElement(rowIndex === 0 ? "th" : "td");
      if (editable) {
        const input = document.createElement("input");
        input.className = "cell-input";
        input.value = cell;
        input.dataset.row = String(rowIndex);
        input.dataset.col = String(cellIndex);
        td.appendChild(input);
      } else {
        td.textContent = cell;
      }
      tr.appendChild(td);
    });
    table.appendChild(tr);
  });
  return table;
}

// 编辑态的一块
function blockEditor(block, index) {
  const row = document.createElement("div");
  row.className = "block-row editing";
  row.dataset.editor = "1";
  row.dataset.type = block.type;

  const head = document.createElement("div");
  head.className = "block-head";
  head.innerHTML =
    '<span class="block-index">#' + index + '</span><span class="block-tag">' +
    block.type + " 编辑中</span>";
  row.appendChild(head);

  const wrap = document.createElement("div");
  wrap.className = "block-editor";

  if (block.type === "p") {
    const textarea = document.createElement("textarea");
    textarea.value = block.text || "";
    wrap.appendChild(textarea);
  } else if (block.type === "list") {
    const textarea = document.createElement("textarea");
    textarea.value = (block.items || []).join("\n");
    textarea.placeholder = "一行一条，空行会被忽略";
    wrap.appendChild(textarea);
  } else if (block.type === "table") {
    wrap.appendChild(tableElement(block.rows || [], true));
  } else {
    const p = document.createElement("p");
    p.textContent = "这种块暂不支持编辑";
    wrap.appendChild(p);
  }

  row.appendChild(wrap);

  const bar = document.createElement("div");
  bar.className = "block-toolbar";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "primary-button";
  saveBtn.textContent = "保存这块";
  saveBtn.onclick = function () {
    saveBlock(index);
  };

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "secondary-button";
  cancelBtn.textContent = "取消";
  cancelBtn.onclick = function () {
    state.editingIndex = -1;
    renderSection();
  };

  bar.appendChild(saveBtn);
  bar.appendChild(cancelBtn);
  row.appendChild(bar);
  return row;
}

// 从编辑区读回数据，组成后端要的 block
function readEditorBlock() {
  const editor = document.querySelector("[data-editor]");
  if (!editor) {
    throw new Error("没有找到编辑区");
  }
  const type = editor.dataset.type;

  if (type === "p") {
    return { type: "p", text: editor.querySelector("textarea").value };
  }
  if (type === "list") {
    const lines = editor.querySelector("textarea").value.split("\n");
    const items = [];
    lines.forEach(function (line) {
      if (line.trim() !== "") {
        items.push(line.trim());
      }
    });
    return { type: "list", items: items };
  }
  if (type === "table") {
    const rows = [];
    editor.querySelectorAll("tr").forEach(function (tr) {
      const row = [];
      tr.querySelectorAll("input").forEach(function (input) {
        row.push(input.value);
      });
      rows.push(row);
    });
    return { type: "table", rows: rows };
  }
  throw new Error("不支持的块类型：" + type);
}

// ---------------- 块级编辑：调用后端 PATCH ----------------

async function patchBlock(payload) {
  const result = await api("/api/records/" + state.record.id + "/document", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  state.record = result.data; // 后端返回整条记录，直接替换本地状态
  state.editingIndex = -1;
  renderParams();
  renderSection();
  toast(result.msg || "已保存");
}

async function saveBlock(index) {
  try {
    const block = readEditorBlock();
    await patchBlock({
      section: state.section,
      index: index,
      action: "replace",
      block: block,
    });
  } catch (error) {
    toast(error.message);
  }
}

async function deleteBlock(index) {
  if (!window.confirm("确定删除第 " + index + " 块吗？")) {
    return;
  }
  try {
    await patchBlock({ section: state.section, index: index, action: "delete" });
  } catch (error) {
    toast(error.message);
  }
}

async function insertBlock(index) {
  try {
    await patchBlock({
      section: state.section,
      index: index,
      action: "insert",
      block: { type: "p", text: "（新增段落，点「编辑这块」修改内容）" },
    });
  } catch (error) {
    toast(error.message);
  }
}

// ---------------- 风险预审展示 ----------------

function renderRisks() {
  const list = $("riskList");
  list.innerHTML = "";

  if (!state.record || !state.record.risks || state.record.risks.length === 0) {
    list.innerHTML = '<p class="empty-text">暂无风险</p>';
    $("riskCount").textContent = "0 项";
    $("highRisk").textContent = "0";
    $("mediumRisk").textContent = "0";
    $("lowRisk").textContent = "0";
    return;
  }

  let high = 0;
  let medium = 0;
  let low = 0;

  state.record.risks.forEach(function (item) {
    const level = (item.level || "LOW").toUpperCase();
    if (level === "HIGH") {
      high = high + 1;
    } else if (level === "MEDIUM") {
      medium = medium + 1;
    } else {
      low = low + 1;
    }

    const row = document.createElement("div");
    row.className = "block-row";

    const head = document.createElement("div");
    head.className = "block-head";
    head.innerHTML =
      '<span class="block-tag">' + (LEVEL_LABELS[level] || level) + "风险</span>" +
      "<strong>" + (item.title || "") + "</strong>";
    row.appendChild(head);

    const desc = document.createElement("p");
    desc.textContent = item.description || "";
    row.appendChild(desc);

    if (item.suggestion) {
      const tip = document.createElement("p");
      tip.textContent = "建议：" + item.suggestion;
      row.appendChild(tip);
    }
    list.appendChild(row);
  });

  $("riskCount").textContent = state.record.risks.length + " 项";
  $("highRisk").textContent = String(high);
  $("mediumRisk").textContent = String(medium);
  $("lowRisk").textContent = String(low);
}

function renderAll() {
  renderParams();
  renderTabs();
  renderSection();
  renderRisks();
}

// ---------------- 记录列表 / 下载 ----------------

async function loadRecords(keyword) {
  try {
    let url = "/api/records?page=1&size=10";
    if (keyword) {
      url = url + "&keyword=" + encodeURIComponent(keyword);
    }
    const result = await api(url);
    state.records = result.data.items || [];
    $("recordsTotal").textContent = "共 " + result.data.total + " 条";
    renderRecordTable();
  } catch (error) {
    toast("记录加载失败：" + error.message);
  }
}

function renderRecordTable() {
  const tbody = $("recordTableBody");
  tbody.innerHTML = "";

  if (state.records.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6" class="empty-text">还没有记录</td>';
    tbody.appendChild(tr);
    return;
  }

  state.records.forEach(function (item) {
    const tr = document.createElement("tr");

    const no = document.createElement("td");
    no.textContent = item.generation_no;
    tr.appendChild(no);

    const title = document.createElement("td");
    title.textContent = item.title;
    tr.appendChild(title);

    const category = document.createElement("td");
    category.textContent = (item.parameters || {}).category_name || "-";
    tr.appendChild(category);

    const risk = document.createElement("td");
    risk.textContent = String((item.risks || []).length);
    tr.appendChild(risk);

    const time = document.createElement("td");
    time.textContent = String(item.create_time || "").slice(0, 16);
    tr.appendChild(time);

    const actions = document.createElement("td");
    const box = document.createElement("div");
    box.className = "record-actions";

    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.textContent = "查看";
    openBtn.onclick = function () {
      openRecord(item.id);
    };

    const downloadBtn = document.createElement("button");
    downloadBtn.type = "button";
    downloadBtn.textContent = "下载";
    downloadBtn.onclick = function () {
      downloadRecord(item.id);
    };

    box.appendChild(openBtn);
    box.appendChild(downloadBtn);
    actions.appendChild(box);
    tr.appendChild(actions);

    tbody.appendChild(tr);
  });
}

async function openRecord(id) {
  try {
    const result = await api("/api/records/" + id);
    state.record = result.data;
    state.section = "techSpec";
    state.editingIndex = -1;
    $("editState").textContent = "编号 " + state.record.generation_no;
    $("exportBtn").disabled = false;
    renderAll();
    switchView("workspace");
  } catch (error) {
    toast(error.message);
  }
}

// 下载必须走 fetch + blob：浏览器直接跳转会丢掉 Authorization 头，必然 401
async function downloadRecord(id) {
  try {
    const response = await fetch("/api/records/" + id + "/download", {
      headers: { Authorization: "Bearer " + state.token },
    });
    if (!response.ok) {
      throw new Error("下载失败：" + response.status);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "采购文件_" + id + ".docx";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast("已开始下载");
  } catch (error) {
    toast(error.message);
  }
}

// ---------------- 启动 ----------------

async function boot() {
  $("loginForm").addEventListener("submit", doLogin);
  $("logoutBtn").addEventListener("click", doLogout);
  $("requirementForm").addEventListener("submit", doGenerate);
  $("demoBtn").addEventListener("click", fillDemo);
  $("exportBtn").addEventListener("click", function () {
    if (state.record) {
      downloadRecord(state.record.id);
    }
  });
  $("copyParamsBtn").addEventListener("click", async function () {
    try {
      await navigator.clipboard.writeText($("structuredOutput").textContent);
      toast("已复制");
    } catch (error) {
      toast("复制失败，请手动选择");
    }
  });
  $("recordSearchBtn").addEventListener("click", function () {
    loadRecords($("recordKeyword").value.trim());
  });
  $("recordResetBtn").addEventListener("click", function () {
    $("recordKeyword").value = "";
    loadRecords("");
  });

  document.querySelectorAll(".nav-item").forEach(function (item) {
    item.addEventListener("click", function () {
      switchView(item.dataset.view);
    });
  });

  // 已登录就直接进主界面
  if (state.token) {
    try {
      const result = await api("/api/auth/me");
      state.me = result.data;
      enterApp();
    } catch (error) {
      state.token = "";
      localStorage.removeItem("jhj_token");
    }
  }
}

boot();
