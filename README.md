# Andy YouTube for Kodi

一个面向电视遥控器使用的轻量 YouTube Kodi 插件。重点解决官方 YouTube 插件在部分设备上搜索、频道浏览不顺手的问题。

## 当前功能

- YouTube 视频搜索
- 热门 / 推荐列表
- 登录后查看“我的订阅”
- 频道视频页
- 搜索历史
- 本地“我喜欢”
- 本地观看历史
- 粘贴 YouTube / Shorts 链接直接播放
- 长按视频进入作者频道
- 长按加入 / 移出本地喜欢
- 下一页
- 刷新当前页
- 中文界面
- 不要求用户填写个人 Google API Key

## 连接自己的 YouTube 账号

v1.1.0 起支持导入用户自己导出的 `cookies.txt`。插件不会要求 Google 密码，也不会把 Cookie 上传到任何项目服务器。

1. 在已经登录 YouTube 的浏览器中导出 **youtube.com** 的 Netscape/Mozilla 格式 `cookies.txt`。
2. 打开 Andy YouTube → **连接我的 YouTube 账号**。
3. 选择 `cookies.txt`。
4. 校验成功后首页会出现 **我的订阅** 和 **YouTube 账号：已连接**。

登录 Cookie 仅保存在 Kodi 的 `addon_data/plugin.video.andyoutube/` 目录中。不要把自己的 `cookies.txt` 上传到 GitHub、发到 Issue、聊天截图或分享给其他人。

YouTube 会轮换账号 Cookie，失效后重新导入即可。yt-dlp 官方也建议对需要登录访问的内容使用 Cookie，而不是依赖 OAuth。

## 播放方式

插件自己负责搜索和浏览。播放采用双后端：

1. 如果 Kodi Python 环境可导入 `yt_dlp`，优先由 yt-dlp 解析直链播放；若已连接账号，会把本地 `cookies.txt` 同时传给 yt-dlp，提高年龄限制、登录后可观看内容的播放成功率。
2. 如果没有 yt-dlp 或解析失败，自动把最终视频 ID 交给已安装的 Kodi 官方 YouTube 插件播放。

账号有权限观看的内容成功率会明显高于匿名模式，但地区封锁、会员权限不足、私人/删除视频仍不能绕过。

## 安装

1. 下载 Release 中的 `plugin.video.andyoutube-x.x.x.zip`。
2. Kodi → 设置 → 插件 → 从 ZIP 文件安装。
3. 打开 **Andy YouTube**。

Kodi 21+ / Python 3。

## 隐私

本地喜欢、观看历史、搜索历史和账号 Cookie 都保存在 Kodi 插件数据目录。本项目没有自己的服务器，不要求 Google 密码，也不会把登录数据写进仓库。

## 说明

YouTube Web / Innertube 接口并非稳定公开 API，YouTube 改版后可能需要更新插件。项目与 Google / YouTube / Kodi 官方无隶属关系。

## 开发

源码目录：`plugin.video.andyoutube/`

```bash
python -m compileall plugin.video.andyoutube
python - <<'PY'
import xml.etree.ElementTree as ET
ET.parse('plugin.video.andyoutube/addon.xml')
ET.parse('plugin.video.andyoutube/resources/settings.xml')
print('XML OK')
PY
```

## License

MIT
