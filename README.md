# 每日政策简报（云端版）

每天北京时间 **11:00**，GitHub Actions 自动抓南京科技政策 → 去重/相关/时效过滤 → 生成网页，
由 GitHub Pages 托管。你只需打开网址查看、复制转发。多客户群＝`daily_brief.py` 里 `CUSTOMERS` 加一条。

## 部署步骤（一次性，约10分钟）

### 1. 建 GitHub 仓库
注册并登录 github.com → 右上角 **New repository** → 名字如 `policy-brief` → 选 **Public** → Create。

### 2. 把本文件夹推上去
本地已初始化好 git。在本文件夹打开终端，执行（把下面网址换成你的仓库地址）：
```
git remote add origin https://github.com/你的用户名/policy-brief.git
git branch -M main
git push -u origin main
```

### 3. 开启网页托管（GitHub Pages）
仓库页 → **Settings** → 左侧 **Pages** → Source 选 **Deploy from a branch** →
分支选 **main**、文件夹选 **/docs** → Save。等几分钟，页面顶部会显示网址：
`https://你的用户名.github.io/policy-brief/`  ← 这就是你每天打开的网址。

### 4. 开启定时器（GitHub Actions）
仓库页 → **Actions** 标签 → 若提示是否启用，点 **I understand…enable** →
左侧选 **daily-brief** → 右侧 **Run workflow** 手动跑一次，确认绿勾成功。
之后每天约 11:00（北京时间）自动跑、自动刷新网页。

## 日常使用
- 每天打开网址，点进客户群子页，**复制转发**贴进微信群。
- 只显示「近60天·没推送过·高相关」的官方消息（四道闸：真实/时效/去重/相关）。

## 加新客户群
编辑 `daily_brief.py` 的 `CUSTOMERS`，仿照已有条目加一条（名字+关键词），push 上去即可，自动多一个子页面。

## 说明
- 抓不到实时数据时自动回退种子数据，网站不会白屏。
- 真实性：只用官方原标题+原文链接，不改写；复制后请人工核对再转发。
- 政策时效以官方当年发布为准。
