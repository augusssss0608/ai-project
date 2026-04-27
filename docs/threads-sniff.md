# Threads For You feed 凭据 sniff 指南

`fetch_threads_home` 需要你自己浏览器登录态下的 graphql 请求细节。这里的所有东西你只做一次，有效期几天到几周；过期了按同样步骤再抓一次。

## 步骤

### 1. 打开 threads.com 并登录

在日常用的 Chrome / Edge 里打开 `https://www.threads.com/`，确认已登录、能刷到 For You feed。

### 2. 打开 DevTools 网络面板

F12 → **Network** 标签 → 右上角筛选框输入 `graphql` → 点 **Fetch/XHR** 过滤。

### 3. 触发 feed 请求

在页面上**稍微往下滚 3-5 下**（或按 R 刷新）。网络面板应该会冒出一串 `/api/graphql` 请求，名字里带 `Homepage` / `HomeFeed` / `Barcelona` 的就是 feed 请求。

### 4. 定位目标请求

点开那条请求，右侧切 **Headers** 标签：

- 右上 **"Request URL"** 应该是 `https://www.threads.com/api/graphql`
- 往下拉 **Request Headers**，找 `x-fb-friendly-name`，值大概率是 `BarcelonaHomepageFeedRootQuery` 或类似（写到凭据 json 里）。如果你看到有多条都带 Barcelona，挑 friendly name 最像"主页 feed"的那条；一般是请求体量最大、带 25 个 edge 的那条。

### 5. 抠三块内容

打开同一个请求的 **Payload** 标签（或直接 Right-Click → Copy → Copy as cURL）。

**① Cookie**（Headers 段）
找到 `Cookie:` 这一行，整行原样拷贝。至少含 `sessionid` / `ds_user_id` / `csrftoken` / `ig_did` / `mid`，不用删多余字段，原样贴就行。

**② Request Headers 里要拷的字段**
- `user-agent`
- `x-fb-lsd`（csrf 相关，动态 token）
- `x-csrftoken`
- `x-ig-app-id`（一般就是 `238260118697367`）
- `x-fb-friendly-name`

其他的 `sec-fetch-*`、`accept-language` 可拷可不拷，但拷上指纹更真。

**③ Form Data (Payload 标签)**
把表单里的每个字段拷进 `.threads-session.json` 的 `body` 段：
- `av`（你的账号 id）
- `fb_dtsg`（动态 csrf token，**过期频率最高**）
- `lsd`（同上）
- `jazoest`
- `doc_id`（persisted query id，Meta 换 schema 时会变）
- `fb_api_caller_class`: 值就是 `RelayModern`
- `fb_api_req_friendly_name`: 同 header 里那个
- `server_timestamps`: `true`
- `__d` / `__user` / `__a` / `__req`: 有就拷，没有就留默认

**④ variables**
Form data 里有一个 `variables=<url encoded json>` 字段，解码后是一个 JSON 对象，里面常见 `first` / `after` / 若干 `__relay_internal__pv__*` provider flag。**整个 JSON 对象原样**放进 `.threads-session.json` 的 `variables` 段，fetcher 跑的时候会把 `after` 替换成翻页游标，其他字段原样 replay。

> 小技巧：Chrome DevTools 点 `variables` 右边那个 `view decoded` 就能看到解码后的 JSON，直接复制。

### 6. 保存为 `data/.threads-session.json`

```bash
cp ~/Desktop/ai-project/data/.threads-session.json.example \
   ~/Desktop/ai-project/data/.threads-session.json
# 用编辑器把你抠到的值填进去
```

文件在 `data/`，`data/` 已 gitignore，不会被 commit。

### 7. 测试

```bash
cd ~/Desktop/ai-project/hooks && python3 -c "
import sys, json, yaml
sys.path.insert(0, '.')
from ai_news.data.fetchers import fetch_one
cfg = yaml.safe_load(open('../.claude/skills/ai-news-filter/sources/threads/fetcher.yaml'))
r = fetch_one('threads', cfg)
print(f'items: {len(r[\"items\"])}, err: {r.get(\"error\")}')
if r['items']:
    print('--- 前 3 条 ---')
    for it in r['items'][:3]:
        print(f'@{it[\"author\"]} [♥ {it[\"like_count\"]}] {it[\"title\"]}')
        print(f'  {it[\"url\"]}')
"
```

期望输出 `items: 50~200, err: None`，并打印几条 post。

## 过期/失效症状

- **立刻返回空 items**：`fb_dtsg` / `lsd` 过期。重新 sniff 步骤 5 的 ③。
- **items 有但 title 全空**：`doc_id` 变了，Meta 换了 query schema，重新 sniff 整个请求。
- **urllib.error.HTTPError 403/401**：`sessionid` 过期，浏览器重新登录再 sniff cookie。

## 合规提醒

- 只抓自己 For You feed 的公开 post 内容，不做点赞/关注/发帖等写操作（项目代码里没有这些方法，别自己加）。
- 不要把 `.threads-session.json` 发出去、commit、或上传 Apify/三方服务。它包含你的 sessionid，等价账号密码。
