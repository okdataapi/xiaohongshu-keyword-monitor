# xiaohongshu-keyword-monitor: monitor RedNote (Xiaohongshu) keywords and brand accounts

[中文说明](#中文说明)

Watch what people post on Xiaohongshu (小红书, RedNote) about a product category, and what a few brand accounts
publish: every run appends the notes' likes, saves, comments and shares to a CSV, then tells you which notes are
new and which ones are taking off.

Xiaohongshu is where Chinese consumers search before they buy: skincare, travel, outdoor gear, baby products,
restaurants. This script turns a keyword such as `露营装备` (camping gear) or `防晒霜 推荐` (sunscreen
recommendations) into a daily record you can read in English or Chinese, chart, or hand to an analyst.

One Python file, standard library only. Run it by hand, from cron, or let the included GitHub Action take a
snapshot every day and commit the CSV. No Xiaohongshu account, no app, no cookies, no browser automation: the data
comes from the [okdata](https://okdata.online/?src=gh-xiaohongshu-keyword-monitor) API at $0.02 per page of about
20 notes.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/okdataapi/xiaohongshu-keyword-monitor/blob/main/xiaohongshu_monitor.ipynb)
Try it in the browser first: the notebook asks for your key, takes a snapshot, then shows a table and a chart.

Good for: brands selling in China or to Chinese travellers, cross-border sellers checking a category before they
launch, agencies reporting on campaigns, and anyone who needs the Xiaohongshu side of market research without a
Chinese phone number.

## What you get

The real report from the second of two runs an hour apart on 2026-11-20 (progress lines on stderr left out;
the authors of individual notes are replaced with `creator A`… and their links removed for this page):

```console
$ python3 monitor.py --keyword "露营装备" --account "562f892fe00dd8540fd94691=迪卡侬DECATHLON"
Xiaohongshu monitor run 2026-11-20T09:19:32Z (previous run 2026-11-20T08:18:20Z)
  keyword:露营装备                                    20 notes
  account:562f892fe00dd8540fd94691 (迪卡侬DECATHLON)  20 notes

New since the last run: 20
  3 likes · creator A · posted 2026-11-20 · 谁能拒绝这套樱花粉露营套组
  3 likes · creator B · posted 2026-11-20 · 露营都带什么
  1 likes · creator C · posted 2026-11-20 · 峰之魂轻量化帐篷，入就对了，有需要找我
  1 likes · creator D · posted 2026-11-20 · #户外用品 #露营装备 #露营好物
  0 likes · creator E · posted 2026-11-20 · #皮卡车改装 #车顶帐篷 #露营装备
  ...and 15 more in the CSV

Biggest movers since the last run (likes + saves + comments):
  +66 interactions (+0.6%) · 迪卡侬DECATHLON · now 3,621 likes, 3,121 saves, 4,668 comments · 抽3️⃣件摇粒绒，迪子不会冻着你！
    https://www.xiaohongshu.com/explore/6af6dc25000000002b01169e
  +44 interactions (+0.8%) · 迪卡侬DECATHLON · now 2,014 likes, 1,017 saves, 2,393 comments · 图3帽子抽1️⃣！我画地为牢，迪卡侬！
    https://www.xiaohongshu.com/explore/6af6b54a000000002b01dd7b
  +7 interactions (+10.9%) · 迪卡侬DECATHLON · now 21 likes, 10 saves, 40 comments · 送蛋白粉！交换二头比心照💪
    https://www.xiaohongshu.com/explore/6afe9cb4000000002b01d8d4
  +5 interactions (+0.3%) · 迪卡侬DECATHLON · now 930 likes, 925 saves, 19 comments · 6条徒步保命指南，所有人熟读并背诵！
    https://www.xiaohongshu.com/explore/6ae478790000000003016bd5
  +4 interactions (+0.6%) · 迪卡侬DECATHLON · now 540 likes, 137 saves, 37 comments · 新品｜升级三合一，羽绒层双面可穿
    https://www.xiaohongshu.com/explore/6ae858b400000000030043ff
```

Each run made 2 calls and cost $0.04. Sorted by `latest`, the whole first page for 露营装备 (camping gear) had
turned over within the hour; the DECATHLON giveaway notes kept collecting comments. Every run appends to
`data/snapshots.csv`, one row per note per run:

```csv
run_at,source,note_id,url,type,author_id,author_name,title,published_at,likes,saves,comments,shares
2026-11-20T09:19:32Z,account:562f892fe00dd8540fd94691,6af6dc25000000002b01169e,https://www.xiaohongshu.com/explore/6af6dc25000000002b01169e,image,562f892fe00dd8540fd94691,迪卡侬DECATHLON,抽3️⃣件摇粒绒，迪子不会冻着你！,2026-11-13T09:50:10.000Z,3621,3121,4668,156
2026-11-20T09:19:32Z,account:562f892fe00dd8540fd94691,6af6b54a000000002b01dd7b,https://www.xiaohongshu.com/explore/6af6b54a000000002b01dd7b,image,562f892fe00dd8540fd94691,迪卡侬DECATHLON,图3帽子抽1️⃣！我画地为牢，迪卡侬！,2026-11-16T10:00:13.000Z,2014,1017,2393,869
```

Open it in a spreadsheet, or load it with pandas and pivot on `note_id` and `run_at` to chart each note's growth.

## Quick start

1. Get an API key at [okdata.online](https://okdata.online/signup/?src=gh-xiaohongshu-keyword-monitor). Pay per
   call, no subscription.
2. Put it in your environment and run:

```bash
git clone https://github.com/okdataapi/xiaohongshu-keyword-monitor
cd xiaohongshu-keyword-monitor
export OKDATA_API_KEY=okd_...     # keep it out of code and commits

# see the plan and the most it can cost first (no key needed)
python3 monitor.py --keyword "露营装备" --account "562f892fe00dd8540fd94691=迪卡侬DECATHLON" --dry-run

# Python 3.9+
python3 monitor.py --keyword "露营装备" --account "562f892fe00dd8540fd94691=迪卡侬DECATHLON"
```

The first run saves a baseline. Run it again at least an hour later (or tomorrow) and the report lists new notes and
the biggest movers. Add `--lang zh` for the report in Chinese.

**Finding an account id.** Open the account on xiaohongshu.com: the id is the 24 characters after
`/user/profile/`. You can pass the whole link instead. The account notes list gives each note's author id but not
the name, so add `=NAME` right after the id to label the account in the CSV and the report. Short `xhslink.com`
share links do not work; open them in a browser first and copy the full link.

## Flags

| Flag | Default | What it does |
|---|---|---|
| `--keyword TEXT` | | Search keywords, as you would type them into the Xiaohongshu search box. Repeat for more. |
| `--account ID` | | An account id or profile link, optionally followed by `=NAME`. Repeat for more. |
| `--sort ORDER` | `latest` | Order of keyword results: `latest`, `popular` or `general` (the app's default ranking). |
| `--pages N` | `1` | Pages per keyword or account, about 20 notes each. |
| `--out DIR` | `data` | Folder for `snapshots.csv`. The file is only ever appended to. |
| `--top N` | `5` | How many new notes and movers the report lists. |
| `--lang en\|zh` | `en` | Language of the report. |
| `--budget USD` | `0.5` | Refuse to start if the run could cost more than this. |
| `--dry-run` | | Print the plan and the most it can cost, then stop. Needs no key. |

The report goes to stdout; progress and the amount spent go to stderr. Rows are saved after each keyword or
account, so a failure halfway keeps what was already fetched.

| Exit code | Meaning |
|---|---|
| `0` | Done |
| `1` | Stopped by an error that would hit every call (bad key, low balance), or every source failed |
| `2` | No key, or a bad flag |
| `3` | The plan could cost more than `--budget`; nothing was called |
| `4` | Done, but some keywords or accounts failed (for example a wrong account id); the rest was saved |

### The CSV

| Column | |
|---|---|
| `run_at` | When the run started, UTC. Every row of one run has the same value. |
| `source` | `keyword:<text>` or `account:<id>` |
| `note_id`, `url` | The note |
| `type` | `image` or `video` |
| `author_id`, `author_name` | Who posted it (for account sources the name is the `=NAME` you gave) |
| `title` | The title, or the start of the text when there is no title, on one line, cut to 100 characters |
| `published_at` | When it was posted, ISO 8601 UTC |
| `likes`, `saves`, `comments`, `shares` | Counts at the time of the run. Xiaohongshu does not show view counts. |

"New" means a note id that is in the latest run and in no earlier run. A keyword search sorted by `latest` is
close to newest first but not strict, so a few older notes rotate in and out of the first page. "Movers" are the
notes found in both of the last two runs, ranked by how much their likes + saves + comments grew (the
"interactions" figure Xiaohongshu marketers use). Text that starts like a spreadsheet formula (`=`, `+`, `-`, `@`)
gets a leading `'` so Excel shows it instead of running it.

Run it once a day, or a few times a day. Two runs less than about an hour apart can come back with the same
numbers: when the API answers from a copy it fetched earlier, the log line for that keyword or account ends with
`(counts as of <time>)`. Leave at least an hour between runs.

## Endpoints and prices

| What | Endpoint | Price |
|---|---|---|
| One page of about 20 notes for a keyword | [`xiaohongshu.notes.search`](https://okdata.online/apis/xiaohongshu/notes/search/?src=gh-xiaohongshu-keyword-monitor) | $0.02 |
| One page of about 20 notes from an account, newest first | [`xiaohongshu.users.notes.list`](https://okdata.online/apis/xiaohongshu/users/notes/list/?src=gh-xiaohongshu-keyword-monitor) | $0.02 |

One keyword and one account, one page each, once a day: 2 calls, $0.04 a day, about $1.20 a month. Before calling
anything, the script reads the current prices from the public catalog (`GET https://api.okdata.online/v1/catalog`,
no key needed), prints the most the run can cost and refuses runs over `--budget`.

The same key also reads note details, comments and replies, account profiles, topic pages and trending topics on
Xiaohongshu, and 29 other platforms: see the [Xiaohongshu endpoints](https://okdata.online/apis/xiaohongshu/?src=gh-xiaohongshu-keyword-monitor).

## Scheduling

### cron

Keep the key in a file only you can read, for example `~/.okdata.env` containing `export OKDATA_API_KEY=okd_...`
(`chmod 600 ~/.okdata.env`), then `crontab -e`:

```cron
# every day at 08:00
0 8 * * * cd "$HOME/xiaohongshu-keyword-monitor" && . "$HOME/.okdata.env" && python3 monitor.py --keyword "露营装备" --account "562f892fe00dd8540fd94691=迪卡侬DECATHLON" >> "$HOME/xhs-monitor.log" 2>&1
```

Give the full path to `python3` if cron cannot find it.

### GitHub Actions

[`.github/workflows/monitor.yml`](.github/workflows/monitor.yml) takes a snapshot every day at 00:23 UTC (08:23 in
China) and commits `data/snapshots.csv` back to the repository, so the history builds up in git.

1. Fork this repository (or use it as a template).
2. Add your key under **Settings → Secrets and variables → Actions → New repository secret**, named `OKDATA_API_KEY`.
3. Under the **Variables** tab, set `KEYWORDS` and `ACCOUNTS`, one entry per line, and optionally `SORT`, `PAGES`
   and `REPORT_LANG` (`en` or `zh`). Without them it monitors `露营装备` and the DECATHLON account.
4. Open the **Actions** tab, enable workflows if GitHub asks (forks start with them off), then
   **monitor → Run workflow** to take the first snapshot now.

The report shows up on each run's summary page. Without the `OKDATA_API_KEY` secret the workflow skips quietly.
The CSV is committed to your repository, so make the repository private if what you watch is nobody else's business.

## Use it from an AI client

The script is a plain REST client. The same Xiaohongshu endpoints are also available to AI assistants through
okdata's remote MCP server, `https://api.okdata.online/mcp`, so you can ask "what are people on Xiaohongshu saying
about camping gear this week? Summarise it in English" or "read the comments under this note and list the
complaints".

Claude Code:

```bash
claude mcp add --transport http okdata https://api.okdata.online/mcp --header 'Authorization: Bearer ${OKDATA_API_KEY}'
```

Cursor, in `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "okdata": {
      "url": "https://api.okdata.online/mcp",
      "headers": {
        "Authorization": "Bearer ${env:OKDATA_API_KEY}"
      }
    }
  }
}
```

Dify: install the [okdata plugin](https://marketplace.dify.ai/plugin/okdata/okdata) from the Dify Marketplace,
then authorize it with your key.

## Notes

- A sample project by [okdata](https://okdata.online/?src=gh-xiaohongshu-keyword-monitor), not affiliated with
  Xiaohongshu. The script only calls the okdata API.
- Public notes and public counts only. Use the data to study products, content and trends, not to build profiles
  of people.
- Tests: `python3 -m unittest discover -s tests`. They run against a local mock server (no network, no cost).
- Issues and ideas are welcome.

---

## 中文说明

盯住小红书上一个品类的关键词，再加几个品牌号：每跑一次，就把笔记的赞、藏、评、转追加到一张 CSV 表里，然后告诉你哪些笔记是新出现的、哪些笔记的互动涨得最快。每天跑一次，表就成了一条时间序列，可以直接画图。

适合品牌方盯竞品和自家号、运营看一个品类最近在火什么、代理商给客户做投放复盘，也适合做出海的团队看国内用户怎么评价同类产品。

一个 Python 文件，只用标准库，Python 3.9 以上就能跑；也可以先在浏览器里试：[Colab 笔记本](https://colab.research.google.com/github/okdataapi/xiaohongshu-keyword-monitor/blob/main/xiaohongshu_monitor.ipynb)。**不用登录小红书，不用 Cookie，不开浏览器**，你自己的小红书账号完全不参与。数据来自 [okdata](https://okdata.online/zh/?src=gh-xiaohongshu-keyword-monitor)，每页约 20 篇笔记 $0.02。

### 快速开始

1. 在 [okdata](https://okdata.online/zh/signup/?src=gh-xiaohongshu-keyword-monitor) 注册拿一个 Key（以 `okd_` 开头），按次付费，不用订阅。
2. 运行：

```bash
git clone https://github.com/okdataapi/xiaohongshu-keyword-monitor
cd xiaohongshu-keyword-monitor
export OKDATA_API_KEY=okd_...     # 别写进代码和提交记录

# 先看计划和最多花多少钱（不用 Key，不花钱）
python3 monitor.py --keyword "露营装备" --account "562f892fe00dd8540fd94691=迪卡侬DECATHLON" --lang zh --dry-run

# 真跑
python3 monitor.py --keyword "露营装备" --account "562f892fe00dd8540fd94691=迪卡侬DECATHLON" --lang zh
```

第一次运行只存一份基准快照。隔一小时以上（或者第二天）再跑同一条命令，报告里就会列出新笔记和互动涨得最多的笔记。一小时内重跑可能拿到同一份缓存数据，日志里会注明 `(counts as of 时间)`。

加 `--lang zh` 的报告长这样（2026-11-20 隔一小时的两次真实运行，第二次的报告；个人博主换成代号、去掉了链接，`--top 3`）：

```console
小红书监控 2026-11-20T09:19:32Z（上次 2026-11-20T08:18:20Z）
  keyword:露营装备                                    20 篇
  account:562f892fe00dd8540fd94691 (迪卡侬DECATHLON)  20 篇

上次以来的新笔记：20 篇
  3 赞 · 博主A · 发布于 2026-11-20 · 谁能拒绝这套樱花粉露营套组
  3 赞 · 博主B · 发布于 2026-11-20 · 露营都带什么
  1 赞 · 博主C · 发布于 2026-11-20 · 峰之魂轻量化帐篷，入就对了，有需要找我
  ……另外 17 篇在 CSV 里

互动涨得最多（赞 + 藏 + 评）：
  +66 互动 (+0.6%) · 迪卡侬DECATHLON · 现在 3,621 赞 3,121 藏 4,668 评 · 抽3️⃣件摇粒绒，迪子不会冻着你！
    https://www.xiaohongshu.com/explore/6af6dc25000000002b01169e
  +44 互动 (+0.8%) · 迪卡侬DECATHLON · 现在 2,014 赞 1,017 藏 2,393 评 · 图3帽子抽1️⃣！我画地为牢，迪卡侬！
    https://www.xiaohongshu.com/explore/6af6b54a000000002b01dd7b
  +7 互动 (+10.9%) · 迪卡侬DECATHLON · 现在 21 赞 10 藏 40 评 · 送蛋白粉！交换二头比心照💪
    https://www.xiaohongshu.com/explore/6afe9cb4000000002b01d8d4
```

**账号 ID 怎么找**：在网页版小红书打开博主主页，地址里 `/user/profile/` 后面那 24 位就是 ID，也可以直接贴整条主页链接。博主笔记列表接口只返回作者 ID、不返回昵称，所以建议在 ID 后面紧跟 `=名字`，CSV 和报告里就会用这个名字。App 里分享出来的`xhslink.com` 短链接不行，先在浏览器里打开，再复制完整地址。

### 参数

| 参数 | 默认 | 作用 |
|---|---|---|
| `--keyword 关键词` | | 搜索关键词，和在小红书搜索框里输入的一样。可以写多个。 |
| `--account ID` | | 账号 ID 或主页链接，可以在后面紧跟 `=名字`。可以写多个。 |
| `--sort 排序` | `latest` | 关键词结果的排序：`latest` 最新、`popular` 最热、`general` 综合 |
| `--pages N` | `1` | 每个关键词或账号取几页，每页约 20 篇 |
| `--out 目录` | `data` | `snapshots.csv` 放在哪个目录，只追加不覆盖 |
| `--top N` | `5` | 报告里列几篇新笔记和几篇涨幅榜 |
| `--lang en\|zh` | `en` | 报告用英文还是中文 |
| `--budget 美元` | `0.5` | 这次运行最多可能花的钱超过这个数就不跑 |
| `--dry-run` | | 只打印计划和最多花多少钱，不调用，不需要 Key |

CSV 每行一篇笔记：运行时间、来源（`keyword:关键词` 或 `account:ID`）、笔记 ID 和链接、图文还是视频、作者、标题（没有标题时取正文开头，最长 100 字）、发布时间，以及赞、藏、评、转四个数。小红书不公开浏览量，所以没有这一列。

「新笔记」指这次出现、以前从没出现过的笔记。按最新排序的搜索结果大体是从新到旧，但不严格，第一页偶尔会轮换进几篇旧笔记。「涨得最多」是在最近两次运行里都出现的笔记，按「赞 + 藏 + 评」的增量排序，也就是小红书运营常说的互动量。

### 花多少钱

一个关键词加一个账号，每天各取一页：每天 2 次调用 $0.04，一个月约 $1.2。脚本调用前会先读公开价格表（不用 Key），打印这次最多花多少钱，超过 `--budget` 就不跑。同一个 Key 还能取小红书的笔记详情、评论、博主资料、话题页和热点，以及其他 29 个平台的数据，见 [小红书接口列表](https://okdata.online/zh/apis/xiaohongshu/?src=gh-xiaohongshu-keyword-monitor)。

### 每天自动跑

- **cron**：把 `export OKDATA_API_KEY=okd_...` 写进只有你能读的 `~/.okdata.env`，再在 `crontab -e` 里加一行，写法见上面英文部分。
- **GitHub Actions**：Fork 本仓库 → 在 Settings → Secrets and variables → Actions 里加 Secret `OKDATA_API_KEY` →
  在 Variables 里设置 `KEYWORDS` 和 `ACCOUNTS`（每行一个），想看中文报告就把 `REPORT_LANG` 设成 `zh` →
  在 Actions 页面运行一次 monitor。之后每天北京时间 08:23 自动拍一份快照并把 CSV 提交回仓库。CSV 会提交到你的仓库里，盯的是竞品的话建议把仓库设成私有。

### 让 AI 直接用

同样的小红书接口也可以通过 okdata 的远程 MCP（`https://api.okdata.online/mcp`）接进 Claude Code、Cursor、Dify，直接问「这周小红书上大家怎么评价露营装备？」「把这篇笔记下面的评论读完，列出差评」。接入方法见[MCP 接入说明](https://okdata.online/zh/mcp/?src=gh-xiaohongshu-keyword-monitor)。

### 说明

- 这是 [okdata](https://okdata.online/zh/?src=gh-xiaohongshu-keyword-monitor) 的示例项目，和小红书官方无关，脚本只调用 okdata 的接口。
- 只取公开笔记和公开数字。请用来研究产品、内容和趋势，不要用来给个人建档。

## License

MIT, see [LICENSE](LICENSE).
