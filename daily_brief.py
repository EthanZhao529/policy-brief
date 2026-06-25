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
    now=NOW_BJ.strftime("%Y-%m-%d %H:%M"); prev={}
    sp=os.path.join(ROOT,"crawl_status.json")
    if os.path.exists(sp):
        try: prev=json.load(open(sp,encoding="utf-8"))
        except Exception: prev={}
    CRAWL_STATUS["at"]=now
    CRAWL_STATUS["last_ok_at"]=prev.get("last_ok_at","")   # 失败时保留上次成功时间，用于提示已停更几天
    try:
        fetched=crawl_list(); CRAWL_STATUS.update(ok=True,mode="live",count=len(fetched),last_ok_at=now)
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

CSS=""":root{--bg:#0a0b12;--txt:#e8edf5;--txt2:#9aa7bd;--txt3:#64708a;--glass:rgba(255,255,255,.045);--glass2:rgba(255,255,255,.075);--line:rgba(255,255,255,.09);--line2:rgba(255,255,255,.16);--accent:#38bdf8;--accent2:#6366f1;--accent3:#6366f1;--gov:#b81d2c;--gov2:#7e1420;--green:#34d399;--red:#fb7185}
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}
body{font-family:'Microsoft YaHei','Segoe UI',-apple-system,Arial,sans-serif;color:var(--txt);background:var(--bg);min-height:100vh;line-height:1.6;-webkit-font-smoothing:antialiased;position:relative;overflow-x:hidden}
body::before,body::after{content:"";position:fixed;border-radius:50%;filter:blur(90px);opacity:.5;z-index:0;pointer-events:none}
body::before{width:48vw;height:48vw;left:-13vw;top:-12vw;background:radial-gradient(circle,#1e3a8a,transparent 70%);animation:d1 22s ease-in-out infinite alternate}
body::after{width:42vw;height:42vw;right:-13vw;bottom:-14vw;opacity:.4;background:radial-gradient(circle,#7e1420,transparent 70%);animation:d2 27s ease-in-out infinite alternate}
@keyframes d1{to{transform:translate(8vw,6vh) scale(1.15)}}@keyframes d2{to{transform:translate(-7vw,-9vh) scale(1.12)}}
.wrap{position:relative;z-index:1;max-width:1000px;margin:0 auto;padding:26px 20px 56px}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:20px}
.logo{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;font-size:23px;font-weight:700;color:#fff;background:linear-gradient(135deg,#c0293a,#8b1e2d 58%,#6f1320);box-shadow:0 6px 20px rgba(160,22,33,.5),inset 0 1px 0 rgba(255,255,255,.35)}
.bt{font-size:17px;font-weight:700;letter-spacing:.5px}.bs{font-size:11.5px;color:var(--txt3);letter-spacing:1px}.sp{flex:1}
.back{font-size:13px;color:var(--txt);text-decoration:none;padding:7px 15px;border:1px solid var(--line);border-radius:999px;background:var(--glass);backdrop-filter:blur(12px);transition:.25s}
.back:hover{border-color:var(--line2);background:var(--glass2);transform:translateY(-1px)}
.hero{position:relative;overflow:hidden;border-radius:22px;padding:28px 30px;margin-bottom:16px;background:linear-gradient(135deg,rgba(56,189,248,.10),rgba(184,29,44,.08));border:1px solid var(--line);backdrop-filter:blur(24px) saturate(140%);box-shadow:0 20px 50px rgba(0,0,0,.45),inset 0 2px 0 rgba(184,29,44,.5)}
.hero h1{font-size:26px;font-weight:800;letter-spacing:.3px;margin-bottom:9px;background:linear-gradient(120deg,#fff,#c3cfe2);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero p{color:var(--txt2);font-size:13.5px;max-width:700px}
.sheen{position:absolute;inset:0;background:linear-gradient(115deg,transparent 35%,rgba(255,255,255,.07) 50%,transparent 65%);transform:translateX(-100%);animation:sheen 7s ease-in-out 2s infinite}
@keyframes sheen{0%,55%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}
.stat{border-radius:16px;padding:16px 18px;background:var(--glass);border:1px solid var(--line);backdrop-filter:blur(16px);transition:.3s}
.stat:hover{transform:translateY(-3px);border-color:var(--line2);background:var(--glass2)}
.stat .n{font-size:27px;font-weight:800;line-height:1}.stat .l{font-size:12px;color:var(--txt3);margin-top:6px}
.s1 .n{color:var(--green)}.s2 .n{color:var(--txt2)}.s3 .n{color:var(--accent)}
.card{position:relative;overflow:hidden;border-radius:18px;padding:18px 20px 16px;margin-bottom:13px;background:var(--glass);border:1px solid var(--line);backdrop-filter:blur(18px) saturate(130%);box-shadow:0 10px 30px rgba(0,0,0,.3);transition:transform .3s cubic-bezier(.2,.8,.2,1),border-color .3s,box-shadow .3s}
.card::before{content:"";position:absolute;top:0;left:0;width:3px;height:100%;background:linear-gradient(var(--gov),var(--gov2));opacity:.9}
.card::after{content:"";position:absolute;inset:0;background:linear-gradient(115deg,transparent 42%,rgba(255,255,255,.06) 50%,transparent 58%);transform:translateX(-130%);transition:transform .8s;pointer-events:none}
.card:hover{transform:translateY(-4px);border-color:var(--line2);box-shadow:0 18px 44px rgba(0,0,0,.5),0 0 0 1px rgba(56,189,248,.18)}
.card:hover::after{transform:translateX(130%)}
.card.expired{opacity:.62}.card.expired::before{background:var(--txt3)}.card.done{opacity:.4}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:9px}
.badges{display:flex;flex-wrap:wrap;gap:6px}
.date{font-size:12px;color:var(--txt3);white-space:nowrap;padding-top:2px}
.title{font-size:16.5px;font-weight:700;line-height:1.5;color:var(--txt)}
.meta{font-size:12.5px;color:var(--txt2);margin-top:8px}
.tag{font-size:11.5px;padding:2px 10px;border-radius:999px;border:1px solid var(--line);background:rgba(255,255,255,.05);color:var(--txt2)}
.tag.new{background:rgba(52,211,153,.15);border-color:rgba(52,211,153,.42);color:#6ee7b7;font-weight:700}
.tag.urg{background:rgba(184,29,44,.22);border-color:rgba(184,29,44,.55);color:#f1a0a8;font-weight:700}
.tag.exp{background:rgba(255,255,255,.04);color:var(--txt3)}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:13px}
.btn{font-size:13px;padding:8px 16px;border-radius:10px;border:1px solid var(--line);cursor:pointer;background:var(--glass);color:var(--txt);text-decoration:none;transition:.25s;backdrop-filter:blur(8px)}
.btn:hover{border-color:var(--line2);background:var(--glass2);transform:translateY(-1px)}
.btn.cp{border:none;color:#fff;font-weight:600;background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 6px 18px rgba(99,102,241,.42)}
.btn.cp:hover{box-shadow:0 10px 26px rgba(99,102,241,.58);filter:brightness(1.08)}
.empty{text-align:center;color:var(--txt3);padding:48px;border:1px dashed var(--line);border-radius:18px;background:var(--glass)}
.legend{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;border-radius:16px;padding:14px 18px;margin-top:18px;background:var(--glass);border:1px solid var(--line);backdrop-filter:blur(14px);font-size:12.5px;color:var(--txt2)}
.legend b{color:var(--txt);font-weight:600}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.foot{margin-top:24px;padding-top:18px;border-top:1px solid var(--line);font-size:12px;color:var(--txt3);text-align:center;line-height:1.9}
.src{margin-top:8px}.src.ok{color:#6ee7b7}
.grp{display:flex;align-items:center;gap:15px;border-radius:18px;padding:20px 22px;margin-bottom:13px;text-decoration:none;color:var(--txt);background:var(--glass);border:1px solid var(--line);backdrop-filter:blur(18px);position:relative;overflow:hidden;transition:.3s}
.grp::after{content:"";position:absolute;inset:0;background:linear-gradient(115deg,transparent 42%,rgba(255,255,255,.06) 50%,transparent 58%);transform:translateX(-130%);transition:transform .8s;pointer-events:none}
.grp:hover{transform:translateY(-4px);border-color:var(--line2);box-shadow:0 18px 44px rgba(0,0,0,.45)}.grp:hover::after{transform:translateX(130%)}
.gi{width:46px;height:46px;border-radius:13px;display:grid;place-items:center;font-size:22px;color:#fff;background:linear-gradient(135deg,#c0293a,#7e1420);box-shadow:inset 0 1px 0 rgba(255,255,255,.3)}
.gt{font-size:16.5px;font-weight:700}.gd{font-size:12.5px;color:var(--txt3);margin-top:3px}.ga{margin-left:auto;color:var(--accent);font-size:22px}
.alert{display:none;background:linear-gradient(135deg,rgba(251,113,133,.18),rgba(244,63,94,.1));color:#fecdd3;border:1px solid rgba(251,113,133,.45);border-left:4px solid var(--red);border-radius:14px;padding:14px 16px;margin-bottom:16px;font-size:14px;font-weight:600;line-height:1.6;backdrop-filter:blur(14px)}
@media(max-width:600px){.wrap{padding:18px 14px 40px}.hero{padding:22px}.hero h1{font-size:21px}.stat .n{font-size:22px}}"""

def alert_block(gen):
    """页面顶部警示条：① 抓取失败(服务器已知)→直接红条，附上次成功时间；
    ② 内置JS兜底——即便连云端任务都没跑(页面好几天没更新)，浏览器也能算出来自动报警。
    健康时整条隐藏，不打扰。"""
    failed = not CRAWL_STATUS.get("ok", True)
    last = CRAWL_STATUS.get("last_ok_at") or CRAWL_STATUS.get("at") or "未知"
    msg = (f'⚠️ 自动抓取失败！当前显示的是缓存数据，可能不是最新政策。上次成功更新：{last}。请尽快处理（找 Claude 排查）。') if failed else ''
    disp = 'block' if failed else 'none'
    return (f'<div id="alert" class="alert" style="display:{disp}">{msg}</div>'
            f'<script>(function(){{var g=new Date("{gen}".replace(/-/g,"/"));'
            f'var d=(Date.now()-g.getTime())/864e5,b=document.getElementById("alert");'
            f'if(b&&b.style.display=="none"&&d>2){{b.style.display="block";'
            f'b.innerHTML="⚠️ 网站已约"+Math.floor(d)+"天未更新，每日自动抓取可能出问题了，请尽快处理（找 Claude 排查）。";}}}})();</script>')

def page_html(cust, rows, gen):
    total=len(rows); n_exp=sum(1 for r in rows if r.get("_dl_state")=="expired"); n_open=total-n_exp
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
            tags+=f'<span class="tag urg">仅剩{days}天</span>'
        elif st=="unknown" and ("申报" in r["title"] or "截止" in r["title"]):
            tags+='<span class="tag">申报中</span>'
        cls="card expired" if st=="expired" else "card"
        meta=f'<div class="meta">申报截止　{dl}</div>' if dl else ''
        fwd=f'【政策提醒】{r["title"]}\n发布：{r["date"] or "见原文"}'+(f'\n申报截止：{dl}' if dl else '')+f'\n原文：{r["link"]}'
        fj=_html.escape(fwd).replace("\n","\\n").replace("'","\\'")
        # 已截止的不给「复制转发」按钮，避免误转发到客户群
        cp_btn='' if st=="expired" else f'<button class="btn cp" onclick="cp(\'{fj}\',\'c{r["id"]}\')">复制转发</button>'
        cards.append(f'''<article class="{cls}" id="c{r["id"]}">
<div class="top"><div class="badges">{tags}</div><span class="date">发布 {r["date"] or "—"}</span></div>
<div class="title">{_html.escape(r["title"])}</div>{meta}
<div class="btns">{cp_btn}<a class="btn" href="{r["link"]}" target="_blank">查看原文</a><button class="btn" onclick="tg('c{r["id"]}')">标记已转发</button></div></article>''')
    body="\n".join(cards) if cards else '<div class="empty">今日暂无符合条件的新消息</div>'
    sok=' ok' if CRAWL_STATUS.get("ok") else ''
    return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{cust["name"]}·政策简报</title><link rel="icon" href="{FAVICON}"><style>{CSS}</style></head><body>
<div class="wrap">
{alert_block(gen)}
<div class="brand"><div class="logo">策</div><div><div class="bt">政策简报</div><div class="bs">POLICY BRIEF · 每日精选</div></div><div class="sp"></div><a class="back" href="./index.html">← 全部客户群</a></div>
<div class="hero"><div class="sheen"></div><h1>{cust["name"]}</h1>
<p>每日自动汇集南京市科技局官方政策，按相关性与申报截止智能排序。<b style="color:#6ee7b7">绿色「新」</b>为近{NEW_DAYS}天发布、优先转发；灰色「已截止」仅存档参考。复制前请人工核对再转发。</p></div>
<div class="stats"><div class="stat s1"><div class="n">{n_open}</div><div class="l">可申报</div></div>
<div class="stat s2"><div class="n">{n_exp}</div><div class="l">已截止 · 存档</div></div>
<div class="stat s3"><div class="n">{total}</div><div class="l">在库通知</div></div></div>
{body}
<div class="legend"><span><span class="dot" style="background:var(--green)"></span><b>新</b> 近{NEW_DAYS}天发布</span><span><span class="dot" style="background:var(--red)"></span><b>仅剩X天</b> 临近截止</span><span><span class="dot" style="background:var(--txt3)"></span><b>已截止</b> 仅存档不可申报</span></div>
<div class="foot">更新：{gen}（北京时间）· 每天 09:30 自动刷新<div class="src{sok}">{source_note()}</div>本服务汇集官方公开信息，仅供参考，请以政府官网原文为准</div>
</div>
<script>function cp(t,id){{navigator.clipboard.writeText(t).then(()=>{{tg(id,1);alert('已复制，可粘贴到群里');}});}}
function tg(id,d){{var e=document.getElementById(id);if(d){{e.classList.add('done');}}else{{e.classList.toggle('done');}}localStorage.setItem(id+location.pathname,e.classList.contains('done')?'1':'');}}
window.onload=function(){{document.querySelectorAll('.card').forEach(e=>{{if(localStorage.getItem(e.id+location.pathname)=='1')e.classList.add('done');}});}};</script></body></html>'''

def index_html(items_count, gen):
    tiles="\n".join(f'<a class="grp" href="./{c["key"]}.html"><div class="gi">策</div><div><div class="gt">{c["name"]}</div><div class="gd">点击查看今日可转发政策</div></div><div class="ga">→</div></a>' for c in CUSTOMERS)
    sok=' ok' if CRAWL_STATUS.get("ok") else ''
    return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>政策简报 · 客户群总览</title><link rel="icon" href="{FAVICON}"><style>{CSS}</style></head><body>
<div class="wrap">
{alert_block(gen)}
<div class="brand"><div class="logo">策</div><div><div class="bt">政策简报</div><div class="bs">POLICY BRIEF · 客户群总览</div></div></div>
<div class="hero"><div class="sheen"></div><h1>客户群总览</h1><p>每天约 09:30 自动刷新。点击对应客户群，查看今日已筛选、可转发的官方政策。</p></div>
{tiles}
<div class="foot">更新：{gen}（北京时间，每天约 09:30 自动刷新）<div class="src{sok}">{source_note()}</div>本服务汇集官方公开信息，仅供参考，请以政府官网原文为准</div>
</div></body></html>'''

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
