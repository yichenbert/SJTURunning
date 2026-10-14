SJTURunPlus 路线工作台更新：**1.1.0**。

- 软件更名为 SJTURunPlus，桌面与 Web 名称同步。
- 替换为新的角色图片图标，调整为 1:1 方形构图与 macOS 风格圆角，提供 macOS、Windows 和 Web 格式。
- README 增加醒目的「你跑不过我你信吗」标题。
- 保留旧配置目录，已有设置和路线可继续使用。

包含浅色桌面界面、地图点选与手绘、OpenStreetMap / 高德切换、本地路线库，以及坐标转换和路线采样改进。应用版本与 macOS 包元数据统一为 1.1.0。

下载并解压对应平台的 ZIP。macOS arm64 适用于 Apple Silicon，采用 ad-hoc 签名，未经 Apple 公证。Windows 安装包由 GitHub Actions 构建，附件出现后可下载；未在本机进行 Windows 桌面实测。

56 项本地离线测试通过（桌面 43、Web 前端 6、Web 服务 7）。未验证真实账号登录、提交、高德在线鉴权或学校成绩认定。

源码参考：[Gnonymous/SJTURunning](https://github.com/Gnonymous/SJTURunning)，基础提交 9938d0d（上游 2.1.1）。原作者 [Labyrinth0419](https://github.com/Labyrinth0419)，二改 [accelerator-s](https://github.com/accelerator-s)，三改 [Gnonymous](https://github.com/Gnonymous)，本版整理与发布 [yichenbert](https://github.com/yichenbert)。保留 MIT 许可证及原版权声明。
