# -*- coding: utf-8 -*-
"""
daily_brief.py — 每日政策简报（云端版，跑在 GitHub Actions 上）
每天北京时间 11:00 由 GitHub Actions 自动运行：
  抓南京科技政策 → 去重 → 相关/时效过滤 → 生成静态网页到 docs/ → 由 GitHub Pages 托管。
你只需打开网址查看、复制转发。多客户群 = CUSTOMERS 配置里加一条 = 多一个子页面。

四道闸：真实(官方原文+链接，不改写) / 时效(近N天) / 去重(state_seen.json) / 相关(关键词)。
抓取：JS 渲染的政府站用 Playwright 渲染后抓；失败回退种子数据，网站永不白屏。
"""
import os, re, json, html as _html
from datetime import datetime, timedelta

ROOT      = os.path.dirname(os.path.abspath(__file__))
DOCS      = os.path.join(ROOT, "docs")
STATE     = os.path.join(ROOT, "state_seen.json")
RECENT_DAYS = 60
NOW_BJ = datetime.utcnow() + timedelta(hours=8)   # GitHub 跑在 UTC，换成北京时间

# === 客户群配置（加群=加一条，自动多一个子页面）===
CUSTOMERS = [
    {"key":"zhongda", "name":"重大科技专项客户群",
     "include":["重大科技专项","重大专项","前沿技术","科技专项","攻关","揭榜","申报指南"],
     "boost":["申报","通知","截止","指南","兑现","资助"]},
    # {"key":"gainian","name":"概念验证中心客户群","include":["概念验证"],"boost":["申报","认定","截止"]},
    # {"key":"chengguo","name":"产学研成果转化客户群","include":["技术转移","成果转化","技术合同"],"boost":["奖补","申报"]},
]
EXCLUDE = ["中标公告","成交公告","采购","询价","招标","结果公告","拟聘","录用","会议纪要","党组","廉政","人事任免"]

SOURCES = [
    {"name":"南京市科技局·通知公告",
     "list_url":"https://kjj.nanjing.gov.cn/njskxjswyh/index.html",
     "art_pat": r'/njskxjswyh/\d{6}/t\d{8}_\d+\.html', "render": True},
]

SEED = [
 ("关于组织申报2025年南京市重大科技专项项目的通知","https://kjj.nanjing.gov.cn/njskxjswyh/202509/t20250930_5661665.html","2025-09-30"),
 ("关于组织申报2026年度江苏省科技重大专项项目的通知","https://kjj.nanjing.gov.cn/njskxjswyh/202605/t20260512_5838515.html","2026-05-12"),
 ("关于转发省科技厅《关于组织开展2026年度前沿技术应用场景建设示范的通知》的通知","https://kjj.nanjing.gov.cn/njskxjswyh/202606/t20260605_5852690.html","2026-06-05"),
]

def load_state():
    if os.path.exists(STATE):
        try: return set(json.load(open(STATE,encoding="utf-8")))
        except: return set()
    return set()
def save_state(seen): json.dump(sorted(seen), open(STATE,"w",encoding="utf-8"), ensure_ascii=False, indent=0)
def norm_date(s):
    m=re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s or "")
    return f"{int(m.group(1))}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""

def fetch_render(src):
    from playwright.sync_api import sync_playwright
    items=[]
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True)
        ctx=b.new_context(ignore_https_errors=True,
                          user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36")
        pg=ctx.new_page(); pg.goto(src["list_url"], timeout=45000, wait_until="domcontentloaded")
        for _ in range(8):
            pg.wait_for_timeout(1500)
            if pg.eval_on_selector_all("a","els=>els.filter(e=>/t\\d{8}_\\d+\\.html/.test(e.href)).length"): break
        anchors=pg.eval_on_selector_all("a","els=>els.map(e=>({href:e.href,txt:e.innerText,par:e.closest('li')?e.closest('li').innerText:''}))")
        b.close()
    pat=re.compile(src["art_pat"]); out=[]
    for a in anchors:
        href=a.get("href","")
        if not pat.search(href): continue
        title=(a.get("txt") or "").strip()
        if len(title)<6: continue
        out.append({"title":title,"link":href,"date":norm_date(a.get("par",""))or norm_date(title),"source":src["name"]})
    return out

def fetch_all():
    items=[]
    for src in SOURCES:
        try:
            if src.get("render"):
                got=fetch_render(src)
                if got: items+=got; print(f"[{src['name']}] 实时抓取 {len(got)} 条"); continue
            print(f"[{src['name']}] 实时为空，回退种子")
        except Exception as e:
            print(f"[{src['name']}] 抓取失败({str(e)[:60]})，回退种子")
        items += [{"title":t,"link":u,"date":d,"source":src["name"]} for (t,u,d) in SEED]
    uniq={}
    for it in items: uniq.setdefault(it["link"], it)
    return list(uniq.values())

def recent(it):
    if not it["date"]: return True
    try: return (NOW_BJ - datetime.strptime(it["date"],"%Y-%m-%d")).days <= RECENT_DAYS
    except: return True
def relevance(it,c):
    if any(x in it["title"] for x in EXCLUDE): return -1
    if not any(k in it["title"] for k in c["include"]): return -1
    return 1 + sum(1 for b in c["boost"] if b in it["title"])

CSS="""body{font-family:'Microsoft YaHei',Arial,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#222;background:#fafafa}
h1{font-size:20px;margin:0 0 4px}.sub{color:#888;font-size:13px;margin-bottom:18px}a.back{font-size:13px;color:#2b6cff;text-decoration:none}
.card{background:#fff;border:1px solid #eee;border-radius:10px;padding:14px 16px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.04)}.card.done{opacity:.45}
.t{font-size:16px;font-weight:600;line-height:1.5}.meta{color:#888;font-size:12px;margin:6px 0}
.tag{display:inline-block;background:#eef4ff;color:#2b6cff;border-radius:4px;padding:1px 7px;font-size:12px;margin-right:6px}.urg{background:#fff0f0;color:#e03131}
.btns{margin-top:10px}button,a.lk{font-size:13px;border:1px solid #ddd;background:#fff;border-radius:6px;padding:6px 12px;margin-right:8px;cursor:pointer;text-decoration:none;color:#333}
button.cp{background:#2b6cff;color:#fff;border-color:#2b6cff}.empty{color:#888;text-align:center;padding:40px}
.grp{display:block;background:#fff;border:1px solid #eee;border-radius:10px;padding:16px;margin:12px 0;text-decoration:none;color:#222;font-size:16px;font-weight:600}"""

def page_html(cust, rows, gen):
    cards=[]
    for r in rows:
        urg=("申报" in r["title"] or "截止" in r["title"])
        tags=f'<span class="tag">{r["source"]}</span>'+('<span class="tag urg">申报/截止 ⚠</span>' if urg else "")
        fwd=f'【政策提醒】{r["title"]}\n发布：{r["date"] or "见原文"}\n原文：{r["link"]}'
        fj=_html.escape(fwd).replace("\n","\\n").replace("'","\\'")
        cards.append(f'''<div class="card" id="c{r["id"]}"><div class="t">{_html.escape(r["title"])}</div>
<div class="meta">发布：{r["date"] or "见原文"}　{tags}</div><div class="btns">
<button class="cp" onclick="cp('{fj}','c{r["id"]}')">复制转发</button>
<a class="lk" href="{r["link"]}" target="_blank">查看原文</a>
<button onclick="tg('c{r["id"]}')">标记已转发</button></div></div>''')
    body="\n".join(cards) if cards else '<div class="empty">今日无符合条件的新消息</div>'
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{cust["name"]}·政策简报</title><style>{CSS}</style></head><body>
<a class="back" href="./index.html">← 返回全部客户群</a>
<h1>{cust["name"]}·今日政策简报</h1>
<div class="sub">更新：{gen}（北京时间）｜仅显示「近{RECENT_DAYS}天·未推送过·高相关」官方消息｜复制后请人工核对再转发</div>
{body}
<script>function cp(t,id){{navigator.clipboard.writeText(t).then(()=>{{tg(id,1);alert('已复制，可粘贴到群里');}});}}
function tg(id,d){{var e=document.getElementById(id);if(d){{e.classList.add('done');}}else{{e.classList.toggle('done');}}localStorage.setItem(id+location.pathname,e.classList.contains('done')?'1':'');}}
window.onload=function(){{document.querySelectorAll('.card').forEach(e=>{{if(localStorage.getItem(e.id+location.pathname)=='1')e.classList.add('done');}});}};</script></body></html>'''

def index_html(items_count, gen):
    links="\n".join(f'<a class="grp" href="./{c["key"]}.html">{c["name"]} →</a>' for c in CUSTOMERS)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>政策简报</title><style>{CSS}</style></head><body>
<h1>政策简报 · 客户群总览</h1>
<div class="sub">更新：{gen}（北京时间，每天约11:00自动刷新）｜点进对应客户群查看今日可转发消息</div>
{links}</body></html>'''

def main():
    os.makedirs(DOCS, exist_ok=True)
    seen=load_state(); items=fetch_all(); gen=NOW_BJ.strftime("%Y-%m-%d %H:%M")
    new_links=set()
    for c in CUSTOMERS:
        scored=[]
        for it in items:
            if it["link"] in seen or not recent(it): continue
            sc=relevance(it,c)
            if sc<0: continue
            scored.append({**it,"score":sc})
        scored.sort(key=lambda x:-x["score"])
        for i,r in enumerate(scored): r["id"]=i
        open(os.path.join(DOCS,f'{c["key"]}.html'),"w",encoding="utf-8").write(page_html(c,scored,gen))
        print(f'  {c["name"]}: {len(scored)} 条')
        for r in scored: new_links.add(r["link"])
    open(os.path.join(DOCS,"index.html"),"w",encoding="utf-8").write(index_html(len(items),gen))
    seen|=new_links; save_state(seen)
    print(f"完成。新增去重 {len(new_links)} 条。网页已写入 docs/")

if __name__=="__main__":
    main()
