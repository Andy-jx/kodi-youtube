# Andy YouTube for Kodi

一个面向电视遥控器使用的轻量 YouTube Kodi 插件。重点解决官方 YouTube 插件在部分设备上搜索、频道浏览不顺手的问题。

## 当前功能

- YouTube 视频搜索
- 热门 / 推荐列表
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

## 播放方式

插件自己负责搜索和浏览。播放采用双后端：

1. 如果 Kodi Python 环境可导入 `yt_dlp`，优先由 yt-dlp 解析直链播放。
2. 如果没有 yt-dlp，自动把最终视频 ID 交给已安装的 Kodi 官方 YouTube 插件播放。

这样避免把经常变化的 YouTube 签名解密代码硬编码进本插件，同时仍然绕开官方插件不方便的搜索界面。

## 安装

1. 下载 Release 中的 `plugin.video.andyoutube-x.x.x.zip`。
2. Kodi → 设置 → 插件 → 从 ZIP 文件安装。
3. 打开 **Andy YouTube**。

Kodi 21+ / Python 3。

## 隐私

本插件的本地喜欢、观看历史和搜索历史保存在 Kodi 插件数据目录，不上传到本项目服务器。本项目没有自己的服务器，也不要求 Google API Key、Google 密码或 YouTube Cookie。

## 说明

YouTube Web / Innertube 接口并非稳定公开 API，YouTube 改版后可能需要更新插件。项目与 Google / YouTube / Kodi 官方无隶属关系。

## 开发

源码目录：`plugin.video.andyoutube/`

基础静态检查：

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
