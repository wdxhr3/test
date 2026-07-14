# 第三方运行环境与素材

本仓库只分发 Codex 桌宠控制层、安装脚本、测试、图标和说明，不分发 PNGTuber Remix 程序或任何创作者制作的 `.pngRemix` 模型。

## 运行所需内容

### 1. Python 环境

- Windows 上可用的 Python 3。
- `requirements.txt` 中声明的 `PyQt5` 和 `pywin32`。

安装命令：

```powershell
python -m pip install -r requirements.txt
```

### 2. PNGTuber Remix 完整发行目录

当前使用的 PNGTuber Remix V1.4 不是只有一个 EXE。实际发行目录至少包含：

- `PNGTuber-Remix.exe`
- `PNGTuber-Remix.pck`
- 发行包附带的 DLL，例如 `godotgif...dll` 和 `libgdexample...dll`

不同版本的文件可能不同，因此请保留官方下载或素材包附带的完整程序目录，不要只复制 EXE。本仓库不会重新分发这些二进制文件。

### 3. 获得授权的角色模型

需要至少一个 `*.pngRemix` 模型。模型由其创作者持有相应权利，本仓库不会上传、复制、解包或重新分发模型。

## 首次启动

双击 `run_pet.bat` 后，程序会先在项目目录及子目录中查找 `PNGTuber-Remix.exe` 和 `*.pngRemix`。找不到时会弹窗要求选择。路径只写入 Git 忽略的 `runtime/user_config.json`。

为了减少配置步骤，可以自行建立如下本地结构；这些第三方文件仍会被 `.gitignore` 排除：

```text
codex_desktop_pet/
├─ PNGTuber/
│  ├─ PNGTuber-Remix.exe
│  ├─ PNGTuber-Remix.pck
│  └─ ...发行包附带的 DLL
└─ models/
   └─ your-character.pngRemix
```

请分别遵守 PNGTuber Remix 和角色模型创作者提供的许可、版权声明与使用条件。

