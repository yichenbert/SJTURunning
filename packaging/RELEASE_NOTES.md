SJTURunPlus **1.2.0**：桌面与 Web 界面外观更新。

- 桌面应用采用简洁黑白灰布局，保留地图绘制、路线库、日期、配速和运行记录功能。
- 右上角提供「跟随系统 / 日间模式 / 夜间模式」，默认跟随系统；手动选择会保存在本机。
- 主窗口、路线库、地图设置、关于与确认弹窗统一适配主题，已有日志也随主题重新着色。
- 地图底图保留原色，强化控件和文字对比度；主题切换保持地图几何布局及原始路线坐标不变。
- Web 页面同步增加双主题和系统自动切换，改进小屏布局、地图尺寸与路线居中。
- 应用显示、Web、服务及 macOS 包元数据统一为 1.2.0，保留原有配置目录。Web 可连接 1.1.0 或 1.2.0 配套服务。

验证：64 项本地离线测试通过（桌面 47、Web 前端 10、Web 服务 7）。检查了双主题渲染、文字对比度、地图点击对齐和主题切换时的坐标保持。系统外观通知在测试中模拟，未改动 macOS 全局设置。未验证真实账号登录、提交、高德在线鉴权或学校成绩认定。

macOS arm64 包适用于 Apple Silicon，采用 ad-hoc 签名，未经 Apple 公证。Windows x64 包由 GitHub Actions 构建，未在本机进行 Windows 桌面实测。

源码参考：[Gnonymous/SJTURunning](https://github.com/Gnonymous/SJTURunning)。原作者 [Labyrinth0419](https://github.com/Labyrinth0419)，二改 [accelerator-s](https://github.com/accelerator-s)，三改 [Gnonymous](https://github.com/Gnonymous)，本版整理与发布 [yichenbert](https://github.com/yichenbert)。保留 MIT 许可证及原版权声明。
