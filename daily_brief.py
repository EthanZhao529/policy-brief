# -*- coding: utf-8 -*-
"""
daily_brief.py — 每日政策简报（云端版，跑在 GitHub Actions 上）
每天北京时间 11:00 由 GitHub Actions 自动运行：
  抓南京科技政策 → 去重 → 相关/时效过滤 → 生成静态网页到 docs/ → 由 GitHub Pages 托管。
你只需打开网址查看、复制转发。多客户群 = CUSTOMERS 配置里加一条 = 多一个子页面。

四道闸：真实(官方原文+链接，不改写) / 时效(近N天) / 去重(按链接) / 相关(关键词)。
抓取：直接 urllib 抓「公示公告」静态列表页(kjj 214/228)→筛相关→并入 items.json；
      抓不到(如海外服务器访问不了政府站)则沿用现有数据，网站永不白屏。
"""
import os, re, json, html as _html
from datetime import datetime, timedelta

ROOT      = os.path.dirname(os.path.abspath(__file__))
DOCS      = os.path.join(ROOT, "docs")
STATE     = os.path.join(ROOT, "state_seen.json")
ITEMS     = os.path.join(ROOT, "items.json")   # 你添加的真实通知（add_news.py 写入）
RECENT_DAYS = 60
NEW_DAYS    = 7    # 发布≤7天标「新」，优先转发
NOW_BJ = datetime.utcnow() + timedelta(hours=8)   # GitHub 跑在 UTC，换成北京时间
# 网站图标：内联 SVG（蓝底白「策」），无需额外文件
FAVICON=("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2064%2064'"
         "%3E%3Crect%20width='64'%20height='64'%20rx='14'%20fill='%232b6cff'/%3E"
         "%3Ctext%20x='32'%20y='46'%20font-size='40'%20text-anchor='middle'%20fill='white'"
         "%20font-family='Microsoft%20YaHei,sans-serif'%3E%E7%AD%96%3C/text%3E%3C/svg%3E")

# === 客户群配置（加群=加一条，自动多一个子页面）===
# 当前唯一客户群＝买了《南京市级重大科技专项申报实操手册》的企业。
# 关键词据手册校准：本专项三专题(重大科技/前沿技术/行业技术)+揭榜挂帅+卡脖子攻关+指南征集+立项公示；
# boost 让「市级重大科技专项申报通知」这条核心通知一发布就排到最前。
CUSTOMERS = [
    {"key":"zhongda", "name":"南京市级重大科技专项申报",
     "include":["重大科技专项","重大专项","科技重大专项","前沿技术","行业技术","卡脖子",
                "关键核心技术","攻关","揭榜","揭榜挂帅","科技专项","申报指南","指南建议"],
     "boost":["市级重大科技专项","南京市重大","南京市级重大","申报","指南","征集","立项","公示","资助","截止"]},
    # {"key":"gainian","name":"概念验证中心客户群","include":["概念验证"],"boost":["申报","认定","截止"]},
    # {"key":"chengguo","name":"产学研成果转化客户群","include":["技术转移","成果转化","技术合同"],"boost":["奖补","申报"]},
]
EXCLUDE = ["中标公告","成交公告","采购","询价","招标","结果公告","拟聘","录用","会议纪要","党组","廉政","人事任免","表彰"]

# 抓取源：南京市科技局「公示公告」栏目——静态 HTML，标题/链接/发布日都在页内，urllib 直接可抓。
# 切记：首页那个通知小部件、以及 njskxjswyh/index.html(信息公开指南页) 是 JS/无列表，别用；必须用这个 214/228 栏目页。
LIST_URL = "https://kjj.nanjing.gov.cn/njskxjswyh/214/228/index_17377.html"
UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}

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

def deadline_info(it):
    """根据 items.json 里可选的 deadline 字段判断申报状态。
    返回 (state, dl_str, days_left)：state ∈ {'open','expired','unknown'}。
    无 deadline 或格式不对 = unknown（照常显示，不做过期处理）。"""
    dl=(it.get("deadline") or "").strip()
    if not dl: return ("unknown","",None)
    try: d=datetime.strptime(dl,"%Y-%m-%d").date()
    except Exception: return ("unknown","",None)
    days=(d-NOW_BJ.date()).days
    return ("expired" if days<0 else "open", dl, days)

def fmt_md(dl):
    m=re.match(r"\d{4}-(\d{2})-(\d{2})", dl or "")
    return f"{m.group(1)}/{m.group(2)}" if m else dl

def crawl_list():
    """抓「公示公告」静态列表页，返回 [{title,link,date,source}]；失败抛异常，由 merge_crawl 兜底。"""
    import ssl, urllib.request
    ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    html=urllib.request.urlopen(urllib.request.Request(LIST_URL,headers=UA),timeout=25,context=ctx).read().decode("utf-8","ignore")
    rows=re.findall(r'<a href="(https://[^"]+/t\d{8}_\d+\.html)"[^>]*title="([^"]+)"[^>]*>.*?</a></span>\s*<span class="d2"[^>]*>(\d{4}-\d{2}-\d{2})</span>', html, re.S)
    return [{"title":re.sub(r"\s+","",t),"link":l,"date":d,"source":"南京市科技局"} for l,t,d in rows]

def any_relevant(title):
    """命中任一客户群关键词、且不在 EXCLUDE → 值得收录（最终显示给哪个群由 relevance 决定）。"""
    if any(x in title for x in EXCLUDE): return False
    return any(k in title for c in CUSTOMERS for k in c["include"])

CRAWL_STATUS={"ok":False,"mode":"cache","count":0,"added":0,"at":""}  # 本次抓取状态，印到网页+写 crawl_status.json

def _write_status():
    json.dump(CRAWL_STATUS, open(os.path.join(ROOT,"crawl_status.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)

def source_note():
    """网页底部「数据源」一行：一眼看出今天是实时抓取还是用了缓存。"""
    s=CRAWL_STATUS
    if s.get("ok"):
        return f'数据源：✅ 实时抓取成功（列表 {s.get("count",0)} 条）· {s.get("at","")}'
    return f'数据源：⚠️ 本次自动抓取未成功，当前显示为上次缓存数据 · {s.get("at","")}'

def merge_crawl():
    """抓列表→筛相关→并入 items.json（按链接去重，保留已有条目的 deadline 等人工信息）。
    抓不到（如海外服务器访问不了政府站）就跳过、沿用现有 items.json，绝不白屏。
    刻意不自动猜测申报截止日（截止日在正文、易猜错）——新抓条目先无 deadline，
    核心通知的截止日由人工核实后补，符合『发付费客户前人工核对』原则。"""
    CRAWL_STATUS["at"]=NOW_BJ.strftime("%Y-%m-%d %H:%M")
    try:
        fetched=crawl_list(); CRAWL_STATUS.update(ok=True,mode="live",count=len(fetched))
        print(f"抓到「公示公告」列表 {len(fetched)} 条")
    except Exception as e:
        CRAWL_STATUS.update(ok=False,mode="cache",error=str(e)[:80])
        print("列表抓取失败，沿用现有 items.json：", str(e)[:80]); _write_status(); return
    data=[]
    if os.path.exists(ITEMS):
        try: data=json.load(open(ITEMS,encoding="utf-8"))
        except: data=[]
    have={it["link"] for it in data}; added=0
    for it in fetched:
        if it["link"] in have or not any_relevant(it["title"]): continue
        data.append(it); have.add(it["link"]); added+=1
        print("  + 新增:", it["date"], it["title"][:30])
    if added: json.dump(data, open(ITEMS,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    CRAWL_STATUS["added"]=added; _write_status()
    print(f"本次新增 {added} 条，items.json 现 {len(data)} 条")

def fetch_all():
    """读 items.json（你用 add_news.py 添加的真实通知）；空则用种子兜底。"""
    data=[]
    if os.path.exists(ITEMS):
        try: data=json.load(open(ITEMS,encoding="utf-8"))
        except: data=[]
    if not data:
        data=[{"title":t,"link":u,"date":d} for (t,u,d) in SEED]
    for it in data: it.setdefault("source","南京市科技局")
    uniq={}
    for it in data: uniq.setdefault(it["link"], it)
    print(f"读到 {len(uniq)} 条已收录通知")
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
.card.expired{opacity:.5;background:#fbfbfb}
.t{font-size:16px;font-weight:600;line-height:1.5}.meta{color:#888;font-size:12px;margin:6px 0}
.tag{display:inline-block;background:#eef4ff;color:#2b6cff;border-radius:4px;padding:1px 7px;font-size:12px;margin-right:6px}.urg{background:#fff0f0;color:#e03131}.exp{background:#f1f3f5;color:#868e96}.new{background:#e6f7ed;color:#0f9d58;font-weight:600}
.btns{margin-top:10px}button,a.lk{font-size:13px;border:1px solid #ddd;background:#fff;border-radius:6px;padding:6px 12px;margin-right:8px;cursor:pointer;text-decoration:none;color:#333}
button.cp{background:#2b6cff;color:#fff;border-color:#2b6cff}.empty{color:#888;text-align:center;padding:40px}
.grp{display:block;background:#fff;border:1px solid #eee;border-radius:10px;padding:16px;margin:12px 0;text-decoration:none;color:#222;font-size:16px;font-weight:600}"""

def page_html(cust, rows, gen):
    cards=[]
    for r in rows:
        st=r.get("_dl_state","unknown"); dl=r.get("_dl_str",""); days=r.get("_dl_days")
        is_new=False
        try: is_new = bool(r["date"]) and st!="expired" and (NOW_BJ.date()-datetime.strptime(r["date"],"%Y-%m-%d").date()).days<=NEW_DAYS
        except Exception: is_new=False
        tags=('<span class="tag new">新</span>' if is_new else '')+f'<span class="tag">{r["source"]}</span>'
        if st=="expired":
            tags+='<span class="tag exp">已截止</span>'
        elif st=="open" and days is not None and days<=14:
            tags+=f'<span class="tag urg">仅剩{days}天 ⚠</span>'
        elif st=="unknown" and ("申报" in r["title"] or "截止" in r["title"]):
            tags+='<span class="tag">申报中</span>'
        cls="card expired" if st=="expired" else "card"
        dlline=f'　申报截止：{dl}' if dl else ''
        fwd=f'【政策提醒】{r["title"]}\n发布：{r["date"] or "见原文"}'+(f'\n申报截止：{dl}' if dl else '')+f'\n原文：{r["link"]}'
        fj=_html.escape(fwd).replace("\n","\\n").replace("'","\\'")
        # 已截止的不给「复制转发」按钮，避免误转发到客户群
        cp_btn='' if st=="expired" else f'<button class="cp" onclick="cp(\'{fj}\',\'c{r["id"]}\')">复制转发</button>\n'
        cards.append(f'''<div class="{cls}" id="c{r["id"]}"><div class="t">{_html.escape(r["title"])}</div>
<div class="meta">发布：{r["date"] or "见原文"}{dlline}　{tags}</div><div class="btns">
{cp_btn}<a class="lk" href="{r["link"]}" target="_blank">查看原文</a>
<button onclick="tg('c{r["id"]}')">标记已转发</button></div></div>''')
    body="\n".join(cards) if cards else '<div class="empty">今日无符合条件的新消息</div>'
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{cust["name"]}·政策简报</title><link rel="icon" href="{FAVICON}"><style>{CSS}</style></head><body>
<a class="back" href="./index.html">← 返回全部客户群</a>
<h1>{cust["name"]}·今日政策简报</h1>
<div class="sub">更新：{gen}（北京时间）｜绿色「新」＝近{NEW_DAYS}天新发布、优先转发；灰色「已截止」仅存档参考｜复制后请人工核对再转发<br><span style="color:#aaa">{source_note()}</span></div>
{body}
<script>function cp(t,id){{navigator.clipboard.writeText(t).then(()=>{{tg(id,1);alert('已复制，可粘贴到群里');}});}}
function tg(id,d){{var e=document.getElementById(id);if(d){{e.classList.add('done');}}else{{e.classList.toggle('done');}}localStorage.setItem(id+location.pathname,e.classList.contains('done')?'1':'');}}
window.onload=function(){{document.querySelectorAll('.card').forEach(e=>{{if(localStorage.getItem(e.id+location.pathname)=='1')e.classList.add('done');}});}};</script></body></html>'''

def index_html(items_count, gen):
    links="\n".join(f'<a class="grp" href="./{c["key"]}.html">{c["name"]} →</a>' for c in CUSTOMERS)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>政策简报</title><link rel="icon" href="{FAVICON}"><style>{CSS}</style></head><body>
<h1>政策简报 · 客户群总览</h1>
<div class="sub">更新：{gen}（北京时间，每天约09:30自动刷新）｜点进对应客户群查看今日可转发消息<br><span style="color:#aaa">{source_note()}</span></div>
{links}</body></html>'''

def main():
    os.makedirs(DOCS, exist_ok=True)
    merge_crawl()                              # 先抓「公示公告」并入 items.json（失败自动跳过、不影响出网页）
    items=fetch_all(); gen=NOW_BJ.strftime("%Y-%m-%d %H:%M")
    for c in CUSTOMERS:
        scored=[]
        for it in items:
            if not recent(it): continue          # 时效：发布超过RECENT_DAYS天自动淡出
            sc=relevance(it,c)                    # 相关：命中该客户群关键词
            if sc<0: continue
            st,dl,days=deadline_info(it)          # 截止：判断是否已过申报截止日
            scored.append({**it,"score":sc,"_dl_state":st,"_dl_str":dl,"_dl_days":days})
        # 排序：可申报的在前、已截止沉底；同组内相关度高的在前，再按发布日期新→旧
        scored.sort(key=lambda x: x.get("date",""), reverse=True)
        scored.sort(key=lambda x: (1 if x["_dl_state"]=="expired" else 0, -x["score"]))
        for i,r in enumerate(scored): r["id"]=i
        open(os.path.join(DOCS,f'{c["key"]}.html'),"w",encoding="utf-8").write(page_html(c,scored,gen))
        n_open=sum(1 for r in scored if r["_dl_state"]!="expired")
        print(f'  {c["name"]}: {len(scored)} 条（其中可申报 {n_open} 条）')
    open(os.path.join(DOCS,"index.html"),"w",encoding="utf-8").write(index_html(len(items),gen))
    print("网页已写入 docs/")

if __name__=="__main__":
    main()
