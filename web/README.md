# SJTURunPlus Web 1.1.0

浏览器入口：**https://yichenbert.github.io/SJTURunning/**

Web 版适配手机、平板和电脑，无需安装桌面应用。前端是无构建依赖的 HTML / CSS / JavaScript；可选 Python 服务复用现有业务模块，无需 PySide6。

## 可以直接使用的功能

- OpenStreetMap 点选、手绘路线；移动、缩放、双指缩放、逐笔撤销和坐标输入。
- 依据 WGS84 路线计算距离与预计用时。
- 当前路线、日期与配速自动保存在当前浏览器；日期及出发时间统一使用北京时间（Asia/Shanghai）。
- 路线库保存、调用、重命名、删除，以及 JSON / GPX 导出。
- 导入桌面版导出的、明确标注 WGS84 的路线文件。
- 导出桌面版 `config.json`，或备份和恢复 Web 版路线及参数。
- 缓存页面资源，首次成功访问后可离线打开工作台；底图仍需要网络，不缓存第三方地图图块。

不同设备的浏览器存储相互独立。用右上角「备份数据」导出，在另一设备「服务连接 → 恢复数据备份」迁移。路线库上限 100 条，每条路线最多 5000 点。Web 首版使用 OpenStreetMap，尚未接入桌面版的高德地图。

## GitHub Pages 的功能边界

GitHub Pages 托管前端，不运行 Python 服务，无法单独完成 Jaccount 登录和记录提交。点击「检查并开始」时，未连接服务会引导至「服务连接」。

配套服务已经实现登录、参数验证、后台任务、进度日志和协作停止接口，复用桌面版 `src.login` 与 `src.main`。公开使用需要你拥有一个可运行 Python 的服务器，以及有效的 HTTPS 域名。前端仅允许 HTTPS 服务；本机 HTTP 开发页面可连接本机 HTTP 服务。

本项目不会把学校账号密码、访问密钥或个人路线打包到 GitHub。浏览器访问密钥和账号信息只保留在当前页面内存；刷新后需重新输入，账号密码只在明确确认任务时发送到你配置的服务端。

## 本机运行配套服务

从仓库根目录操作，Python 3.11 或更高：

```sh
python -m venv .web-venv
source .web-venv/bin/activate
# Windows PowerShell: .web-venv\Scripts\Activate.ps1
pip install -r web/requirements.txt
# 生成随机访问密钥（仅自己保存）
python -c 'import secrets; print(secrets.token_urlsafe(32))'
export SJTU_WEB_TOKEN='填入刚生成的访问密钥'
# Windows PowerShell: $env:SJTU_WEB_TOKEN = '填入刚生成的访问密钥'
python -m web.server --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765`，在「服务连接」填写同一地址和访问密钥。服务必须配置至少 24 字符的密钥；默认仅监听本机。

此方式同时提供前端和 API。直接从 HTTPS 的 GitHub Pages 页面访问本机 HTTP 不受支持。公开部署后在 Pages 页面填写你的 HTTPS 服务地址。

## 服务器部署

可在服务器按上节安装，服务保持监听 `127.0.0.1:8765`，使用 HTTPS 反向代理。提供了 `web/Caddyfile.example`，替换为你的实际域名后使用 Caddy；TLS 证书和域名解析由你的服务器部署负责。

服务默认允许浏览器来源 `https://yichenbert.github.io`。使用其他网页域名时添加 `--allow-origin https://your-frontend.example.com`。该值是 origin，仅包含协议、域名和端口，不含 `/SJTURunning/` 路径。

Docker（从仓库根目录构建）：

```sh
docker build -f web/Dockerfile -t sjtu-run-web .
docker run --rm --name sjtu-run-web \
  -p 127.0.0.1:8765:8765 \
  -e SJTU_WEB_TOKEN \
  sjtu-run-web
```

运行前在环境变量配置访问密钥。公开入口通过 HTTPS 反向代理提供；请勿将访问密钥写入 Git 仓库。

该服务是单所有者模式：掌握访问密钥的设备可查看同一服务内的任务；同时只运行一个任务，保留最近 50 条内存记录，每条最多 500 条日志。服务重启后记录清空。取消任务会在当前网络请求返回后停止，无法撤回已经发送的请求。

## 发布到 GitHub Pages

`.github/workflows/web-pages.yml` 在 Web 或共享业务源码更新后运行前端和模拟服务测试，再把 `web/static` 发布到 GitHub Pages。仓库 Settings → Pages 的 Source 使用 GitHub Actions。无需第三方前端依赖或 Node 构建步骤。

## 验证

```sh
node --test web/tests/core.test.mjs
python -m unittest discover -s web/tests -v
```

测试覆盖路线格式、投影往返、日期和参数校验、桌面版兼容导出、GPX 转义、接口鉴权、来源控制、模拟任务、停止、日志脱敏及配置快照。服务测试的登录和提交均被模拟，不代表真实账号登录、上传成功或学校成绩认定。Docker 和公网 Python 服务需要在你的实际服务器上验证。

## 来源与许可证

参考 [Gnonymous/SJTURunning](https://github.com/Gnonymous/SJTURunning)；原作者 [Labyrinth0419](https://github.com/Labyrinth0419)，二改 [accelerator-s](https://github.com/accelerator-s)，三改 [Gnonymous](https://github.com/Gnonymous)，本版整理与发布 [yichenbert](https://github.com/yichenbert)。保留根目录 MIT License 及原版权声明。
