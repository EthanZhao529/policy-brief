# -*- coding: utf-8 -*-
"""
add_news.py — 把 kjj 通知网址加入简报网站（Plan B 助手式）。
用法：双击 添加.bat → 粘贴一个或多个通知网址(每行一个) → 空行回车 →
  自动抓每条的标题、从网址取日期、写入 items.json、重新生成网页、推送到 GitHub。
日期直接从网址 t20250930 里取，标题用 http 请求取（单篇文章页可正常访问）。
"""
import sys, io, os, re, json, ssl, urllib.request, subprocess
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception: pass

ROOT  = os.path.dirname(os.path.abspath(__file__))
ITEMS = os.path.join(ROOT, "items.json")
CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
UA  = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
SUFFIX = ["-南京市科学技术局","_南京市科学技术局","-南京市人民政府","_南京市人民政府","-南京市科技局"]

def date_from_url(url):
    m=re.search(r'/t(\d{4})(\d{2})(\d{2})_', url)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""

def fetch_title(url):
    try:
        html=urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=25,context=CTX).read().decode("utf-8","ignore")
    except Exception as e:
        print("   抓取出错:", str(e)[:50]); return None
    m=re.search(r'<title>(.*?)</title>', html, re.DOTALL|re.I)
    t=re.sub(r'\s+','',m.group(1)) if m else ""
    for s in SUFFIX: t=t.replace(s,"")
    return t.strip() or None

def load():
    if os.path.exists(ITEMS):
        try: return json.load(open(ITEMS,encoding="utf-8"))
        except: return []
    return []

print("="*56)
print(" 添加政策通知到简报网站")
print(" 把 kjj 通知网址粘贴进来，每行一个；粘完后按一次【空行回车】结束：")
print("-"*56)
urls=[]
while True:
    try: line=input().strip()
    except EOFError: break
    if not line: break
    if line.startswith("http"): urls.append(line)
    else: print("   (忽略非网址)", line[:30])
if not urls:
    print("没有有效网址，退出。"); sys.exit()

data=load(); have={it["link"] for it in data}; added=0
for u in urls:
    if u in have: print("[跳过·已收录]", u[-40:]); continue
    d=date_from_url(u); t=fetch_title(u)
    if not t: print("[失败·抓不到标题]", u[-40:]); continue
    data.append({"title":t,"link":u,"date":d,"source":"南京市科技局"}); have.add(u); added+=1
    print("[已添加]", d, t[:34])
json.dump(data, open(ITEMS,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n本次新增 {added} 条，目前共 {len(data)} 条。")

print("\n重新生成网页 ...")
import daily_brief; daily_brief.main()

print("\n推送到 GitHub（让网站刷新）...")
try:
    subprocess.run(["git","add","-A"], cwd=ROOT)
    subprocess.run(["git","commit","-m","add news"], cwd=ROOT)
    r=subprocess.run(["git","push"], cwd=ROOT)
    print("PUSH OK，过 1-2 分钟网站就更新了。" if r.returncode==0
          else "PUSH 失败 —— 打开 GitHub Desktop 点一下 Push 即可。")
except Exception as e:
    print("git 出错：", str(e)[:60], "—— 改用 GitHub Desktop 点 Push。")
