# Codex Desktop Pet

这是一个 Windows 独立桌宠控制层。角色仍由素材附带的 PNGTuber Remix 渲染，因此不会把原画转换成像素风，也不会重新绘制或解包模型。

## 功能

- 自动发现并启动 PNGTuber Remix、加载选定的 `.pngRemix` 模型并创建透明角色窗口。
- 角色透明悬浮、始终置顶，按住角色可拖动。
- 双击角色打开 ChatGPT/Codex 桌面应用。
- 右键角色可切换 `Shift + 1` 到 `Shift + 0`、`Shift + -` 的原模型表情。
- 通过 Codex 官方 Hooks 自动同步提交问题、等待批准和回答完成状态。
- 独立暖白对话气泡显示问题摘要与模型完整回答，长回答可展开、滚动和复制。
- 完成、等待输入和错误气泡会保留到手动关闭；双击气泡可返回 Codex。
- 系统托盘提供同样的控制菜单。

## 启动与停止

双击 `run_pet.bat` 启动，双击 `stop_pet.bat` 停止。

首次启动时，程序会按以下顺序定位渲染器和模型：

1. 在项目目录及其子目录中自动寻找 `PNGTuber-Remix.exe` 和 `*.pngRemix`。
2. 如果没有找到，弹出文件选择窗口，让你分别选择渲染器和模型。
3. 选择结果保存在本机的 `runtime/user_config.json`；该目录已被 Git 忽略，不会把个人绝对路径提交到仓库。

因此可以把 PNGTuber Remix 完整程序目录和模型放进克隆后的项目目录，程序会自动找到；也可以把它们放在电脑的任意位置，在首次启动时手动选择。请注意 `PNGTuber-Remix.exe` 旁边通常还需要原程序附带的 `.pck` 和 DLL 文件。

本仓库明确不包含、也通过 `.gitignore` 阻止提交任何 `*.pngRemix` 创作者模型，以及 PNGTuber Remix 的 EXE、PCK、DLL 和用户偏好文件。第三方运行环境、Python 依赖与许可边界详见 [`THIRD_PARTY.md`](THIRD_PARTY.md)。

也可以运行 `create_shortcut.ps1` 创建带角色图标的 `启动 Codex 桌宠.lnk`。图标源文件位于 `assets/codex-pet-icon.png`，Windows 多尺寸图标位于 `assets/codex-pet.ico`。

也可以在终端运行：

```powershell
python app.py
```

如果缺少依赖：

```powershell
python -m pip install -r requirements.txt
```

## 控制回答气泡和表情

桌宠在本机 `127.0.0.1:19288` 接收 UDP JSON 指令，只监听本机。

```powershell
python petctl.py say "模型回答已经完成。"
python petctl.py expression 3
python petctl.py state running
python petctl.py state ready --text "测试通过，可以查看结果。"
python petctl.py open
```

状态对应的表情可以在 `pet_config.json` 的 `states` 中调整。不同模型的表情编号含义可能不同，先用右键菜单确认喜欢的表情，再修改映射即可。

当前模型已按实测设置为：普通状态使用 1/2，需要输入使用带汗表情 8，完成使用开心表情 0，失败使用不满表情 6。

## Codex 自动同步

自动同步脚本是 `codex_hook.py`，全局 Hook 配置安装在 `%USERPROFILE%\.codex\hooks.json`。它不会修改或覆盖 `config.toml` 里已有的 `notify` 配置。

Codex 出于安全考虑，会在 Hook 首次运行前要求审查精确命令。请在 Codex 中打开 `/hooks`，确认三个来自 `~/.codex/hooks.json` 的 Hook：

- `UserPromptSubmit`：开始回答时切换为“正在回答”。
- `PermissionRequest`：需要你授权时显示具体工具与原因。
- `Stop`：把 `last_assistant_message` 原样显示为完整最终回答。

信任一次后无需再次操作；只有 Hook 文件内容被修改时才需要重新审查。事件通过 `127.0.0.1:19289` TCP 发送，支持远大于 UDP 数据报的回答。桌宠未运行时事件会进入 `runtime/pending_events.jsonl`，下次启动自动回放。

首次克隆仓库后可以运行：

```powershell
python install_hooks.py
```

安装器会保留现有的其他 Hooks，只替换由本桌宠创建的三个处理器。Windows 命令不会以带引号的可执行文件开头，以兼容 Codex Desktop 的 Hook 解析方式。

## 测试

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests -v
```

测试覆盖长回答展开、完整正文保留、相对时间更新、窗口与模型缩放，以及克隆仓库后的路径自动发现和本地配置保存。

## 配置

`pet_config.json` 包含可提交到仓库的公共默认配置，例如窗口尺寸、Codex Windows App ID、事件端口和状态表情映射。个人的渲染器和模型绝对路径保存在 `runtime/user_config.json`。当前自动化坐标针对素材附带的 PNGTuber Remix V1.4。

`renderer.zoom_steps` 是参考尺寸下的原生镜头缩放基准。程序会结合 `reference_width`、`reference_height` 和当前窗口尺寸自动追加缩放；当前 `540×338` 窗口会从基准 `-6` 自动调整为 `-8`，以保留角色、猫和桌面的完整构图。

模型包包含作者的版权声明；本项目不会解密或重新分发模型素材。请只在素材授权允许的范围内使用。

