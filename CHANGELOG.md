# Changelog

## 1.2.0

- 停止把“热门 / 推荐”和“我的订阅”建立在自写的 YouTube 网页 renderer 递归解析器上；核心列表改用 yt-dlp 已明确支持并持续维护的 YouTube 专用提取器：`:ytrec`（推荐）、`:ytsubs`（订阅，需要 Cookie）、`ytsearch:`（搜索）。
- `yt_dlp` 继续只在真正打开在线列表或播放视频时按需加载；Kodi 首页保持纯本地，不再因为网络抓取或重型依赖影响首页响应。
- 推荐缓存 3 分钟、订阅缓存 2 分钟、搜索缓存 15 分钟；首次打开需要联网，返回同一列表时可直接命中本地缓存。
- 搜索以 yt-dlp `ytsearch` 为主，并保留原 Innertube 搜索作为第二条独立兜底，避免搜索单点失效。
- 列表提取统一限制首批数量并使用 flat/lazy playlist 模式，避免递归扫描整份巨大 `ytInitialData` 导致 Kodi 卡顿。
- 继续继承 1.1.6 的 Cookie 保留策略、内置 yt-dlp/EJS、Windows Deno，以及账号限制视频的 Cookie 感知播放路径。

## 1.1.6

- Cookie 导入改为“本地格式校验为硬条件、在线账号探测为提示条件”：只要 `cookies.txt` 包含有效的 YouTube 账号 Cookie，就不会因为一次在线探测未确认而被自动删除。
- YouTube 在线验证可能受到页面结构、同意页、临时挑战或地区返回差异影响；现在探测失败时保留 Cookie，并允许继续实际测试“我的订阅”、搜索和账号授权/年龄限制视频播放。
- 首页账号状态文案改为“Cookie 已导入”，避免把一次未确认的在线探测误报成完全连接成功或完全失效。
- 账号状态页明确区分“Cookie 已导入”和“在线验证通过”，并继续提供移除 Cookie 的入口。
- 继承 1.1.5 的内置 yt-dlp/EJS、Windows Deno 与搜索双路径兜底。

## 1.1.5

- 发布 ZIP 在构建时内置最新 `yt-dlp` 与 `yt-dlp-ejs`，Kodi 不再依赖系统里是否恰好装有 `yt_dlp` Python 模块。
- Windows 发布包同时内置官方 Deno 运行时，让 yt-dlp 可以处理 YouTube 2026 使用的 JavaScript challenge；播放账号可观看的登录/年龄限制视频时会自动携带已导入的 `cookies.txt`。
- Cookie 感知的 yt-dlp 解析失败时写入 `AndyYouTube-debug.log`，不记录 Cookie 内容；自动模式仍保留官方 YouTube 插件作为公共视频最后兜底。
- 播放解析器在顶层 URL 缺失时，会从 yt-dlp 返回的格式中选择带音视频的可直接播放流。
- 搜索保留 Innertube 主路径，并新增 YouTube 浏览器搜索结果页 `ytInitialData` 兜底；接口结构变化时不至于直接失去搜索。

## 1.1.4

- “我的订阅”首次加载改为直接请求 `https://www.youtube.com/feed/subscriptions`，使用已导入 Cookie 读取该账号真实网页中的 `ytInitialData`。
- “热门 / 推荐”首次加载优先直接解析 YouTube 首页 `ytInitialData`，不再只依赖内部 browseId。
- 继续保留 Innertube continuation / browse 作为翻页和兜底路径。
- 新增更宽松的新式视频节点识别：`videoId` / `contentId`、`lockupViewModel`、`videoCardViewModel`、Shorts/Reel 等结构均可递归提取。
- 如果 YouTube 返回的数据确实无法解析，不再静默显示空白，而是提示打开“诊断信息”。

## 1.1.3

- 修复“我的订阅”打开后空白：适配 YouTube 2026 正在使用的 `lockupViewModel`、`videoCardRenderer` 等新版 feed renderer。
- `richItemRenderer` 内的新式视频结构现在可以递归识别，不再只认旧 `videoRenderer`。
- YouTube 已停用旧 `FEtrending` feed，“热门 / 推荐”改用当前 `FEwhat_to_watch` 首页推荐 feed。
- 保留旧 renderer 兼容，搜索、频道页与新版 feed 可同时解析。

## 1.1.2

- 修复 Kodi 21 部分环境中 `getSettingString()` 触发 `TypeError: Invalid setting type`，导致 Cookie 验证中断的问题。
- 设置读取统一改用兼容性更好的文本读取方式，账号验证与播放后端均覆盖。
- 新增插件独立诊断日志 `AndyYouTube-debug.log`，不再完全依赖 Kodi 总日志。
- 首页新增“诊断信息”，可直接查看插件自己的诊断记录与日志路径。
- 诊断日志只记录阶段、错误类型和堆栈，不写入 Cookie 内容。

## 1.1.1

- 修复 Android / Kodi 文件选择器导入 `cookies.txt` 时可能报错的问题。
- Cookie 文件复制改用 Kodi VFS，兼容更多 Android 文件路径与内容 URI。
- 增加 VFS 失败后的二次读取写入兜底。
- 首页账号状态改为本地 Cookie 检查，避免每次进入首页都发账号验证请求。
- 导入失败、格式错误、在线验证失败现在会显示更明确的提示，并写入 `kodi.log`。
- Cookie 文件写入后尽量设置为仅当前用户可读写。

## 1.1.0

- 支持导入用户自己的 YouTube `cookies.txt`。
- 首页增加“我的订阅”和账号状态。
- 订阅页使用登录态访问。
- yt-dlp 播放时携带 Cookie，提高需要登录/年龄确认视频的播放成功率。

## 1.0.0

- 首个可测试版本。
- YouTube 搜索、热门/推荐、频道视频页。
- 本地喜欢、观看历史、搜索历史。
- 支持 YouTube / Shorts 链接识别。
- 长按进入作者频道、加入/移出喜欢。
- 支持分页与刷新。
- 不要求个人 Google API Key。
- 播放优先 yt-dlp，可回退 Kodi 官方 YouTube 插件。
