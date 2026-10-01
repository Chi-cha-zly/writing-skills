import re, sys, zipfile, posixpath, html, shutil
from pathlib import Path

SRC = sys.argv[1] if len(sys.argv) > 1 else "novel.epub"
N_CHAPTERS = 12        # 完整保留的章节数（均匀分布在全书）
N_PARAS = 150          # 额外挑出的高描写密度段落数
BATCH_CHARS = 25000    # 每批字数
MIN_CHAPTER = 500      # 少于这个字数的文件（封面、版权页）跳过
OUT = Path("slices") / Path(SRC).stem.strip()   # 每本书单独一个文件夹
shutil.rmtree(OUT, ignore_errors=True); OUT.mkdir(parents=True)

# 1. 按 epub 的阅读顺序（spine）读出每个章节文件
z = zipfile.ZipFile(SRC)
opf_path = re.search(r'full-path="([^"]+)"', z.read("META-INF/container.xml").decode()).group(1)
opf = z.read(opf_path).decode("utf-8", "ignore")
base = posixpath.dirname(opf_path)
items = {}
for tag in re.findall(r"<(?:\w+:)?item\b[^>]*>", opf):   # 兼容 <item> 和 <opf:item>
    i, h = re.search(r'\bid="([^"]+)"', tag), re.search(r'\bhref="([^"]+)"', tag)
    if i and h: items[i.group(1)] = h.group(1)
order = re.findall(r'<(?:\w+:)?itemref\b[^>]*?idref="([^"]+)"', opf)

def to_paras(xhtml):
    body = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", xhtml)
    body = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|li)>", "\n", body)
    body = html.unescape(re.sub(r"<[^>]+>", "", body))
    return [p.strip() for p in body.split("\n") if p.strip()]

chapters = []
for idref in order:
    href = items.get(idref)
    if not href: continue
    path = posixpath.normpath(posixpath.join(base, href.split("#")[0]))
    try: xhtml = z.read(path).decode("utf-8", "ignore")
    except KeyError: continue
    paras = to_paras(xhtml)
    chars = sum(map(len, paras))
    if chars < MIN_CHAPTER: continue
    if any(k in "".join(paras[:5]) for k in ("目录", "Table Of Contents")) and chars / len(paras) < 25:
        continue                                          # 跳过目录页
    m = re.search(r"(?is)<h[1-3][^>]*>(.*?)</h[1-3]>", xhtml)
    title = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else paras[0][:20]
    if paras[0] == title: paras = paras[1:]               # 去掉正文里重复的标题行
    chapters.append((title, paras))
if not chapters: sys.exit("没有识别到章节，这本 epub 的结构可能比较特殊，请检查 content.opf")
print(f"共识别 {len(chapters)} 章，{sum(sum(map(len, p)) for _, p in chapters)} 字")

# 2. 均匀抽取完整章节（开头、中段、结尾都覆盖）
step = max(1, len(chapters) // N_CHAPTERS)
picked = set(range(0, len(chapters), step)[:N_CHAPTERS])

# 3. 给其余章节的段落打"描写密度"分：感官词多、对话少、长度适中
SENSE = "光影色雾雨雪风云月霞暮晨夜灯烛香气息声响寂静凉暖冷湿草木花叶枝檐窗瓦苔石水波涟漪尘"
def score(p):
    if len(p) < 80 or len(p) > 600: return 0
    quotes = len(re.findall(r"[“”「」\"]", p))
    return sum(p.count(c) for c in SENSE) / len(p) * 100 - quotes * 2

cands = []
for i, (title, paras) in enumerate(chapters):
    if i in picked: continue
    for p in paras:
        s = score(p)
        if s > 0: cands.append((s, i, title, p))
cands.sort(reverse=True)
top = sorted(cands[:N_PARAS], key=lambda x: x[1])  # 按原书顺序排

# 4. 组装并按字数分批输出
blocks = [f"【完整章节｜{chapters[i][0]}】\n" + "\n".join(chapters[i][1]) for i in sorted(picked)]
blocks += [f"【片段｜{t}｜类型：___｜喜欢原因：___】\n{p}" for _, _, t, p in top]

batch, size, n = [], 0, 1
for b in blocks + [None]:
    if batch and (b is None or size + len(b) > BATCH_CHARS):
        (OUT / f"batch_{n:02d}.txt").write_text("\n\n".join(batch), encoding="utf-8")
        n, batch, size = n + 1, [], 0
    if b: batch.append(b); size += len(b)
print(f"输出 {n-1} 批到 {OUT}/，合计 {sum(map(len, blocks))} 字")
