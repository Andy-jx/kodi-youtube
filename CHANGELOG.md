# Changelog

## 1.1.2

- 修复 Kodi 21 部分环境中 `getSettingString()` 触发 `TypeError: Invalid setting type`，导致 Cookie 验证中断的问题。
- 设置读取统一改用兼容性更好的文本读取方式，账号验证与播放后端均覆盖。
- 新增插件独立诊断日志 `AndyYouTube-debug.log`，不再完全依赖 Kodi 总日志。
- 首页新增“诊断信息”，可直接查看插件自己的诊断记录与日志路径。
- 诊断日志只记录阶段、错误类型和堆栈，不写入 Cookie 内容。

## 1.1.1

- 修复 Android / Kodi 文件选择器导入 `cookies.txt` 时可能报错的问题。
- Cookie 文件复制改用 Kodi VFS，兼容更多 Android 文件路径与内容 URI。
- 增加 VFS 复制失败后的二次读取写入兜底。
- 首页账号状态改为本地 Cookie 检查，避免每次进入首页都发账号验证请求。
- 导入失败、格式不正确、在线验证失败现在会显示更明确的提示，并写入 `kodi.log`。
- Cookie 文件保存后尽量设置为仅当前用户可读写。

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
- 长按视频进入频道、加入/移出喜欢。
- 支持分页与刷新。
- 不要求个人 Google API Key。
- 播放优先 yt-dlp，可回退 Kodi 官方 YouTube 插件。
