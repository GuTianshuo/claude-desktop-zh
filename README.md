# claude-desktop-zh

给 Claude Desktop（Linux 版）补上中文界面的脚本。

官方桌面端目前只发布 11 种界面语言（en、de、fr、ko、ja、es-419、es-ES、it、hi、pt-BR、id），
没有中文。主界面的 4.4 万条文案里中文是空的，桌面外壳自带的中文包只有 893/1310 条，
既没有补全，也没有在语言列表里开放。

这个项目做的事很简单：把中文词条补进应用自带的两个 asar 归档，并把 `zh-Hans` 加进语言白名单。

效果：

- 设置里的语言列表会多出「中文（简体）」
- 系统语言是中文时，启动后自动使用中文
- 原有的语言选项不受影响，随时可以在界面里切回去

## 改了哪些地方

| 文件 | 内容 |
| --- | --- |
| `resources/ion-dist.asar` | 新增 `i18n/zh-Hans.json` 与 `i18n/dynamic/zh-Hans.json`；3 处硬编码的语言白名单加入 `zh-Hans` |
| `resources/app.asar` | 主进程的系统语言映射加入 `zh → zh-Hans`；补齐外壳词条缺口 |

界面语言由本机语言和用户选择共同决定，词条通过 `app://` 协议从 asar 内的
`/i18n/<locale>.json` 读取。文件存在、白名单放行，语言就会真正生效。
补完之后 `<html lang="zh-Hans">`，界面文字也是中文，这点已在 5.11492.5 上验证过。

## 用法

依赖：Node（脚本用 `@electron/asar` 解包和打包）、Python 3.10+。

```bash
git clone https://github.com/GuTianshuo/claude-desktop-zh
cd claude-desktop-zh
export WORK=~/.cache/claude-desktop-zh

# 1. 从已安装的应用里取出归档（只读，不修改系统文件）
python3 scripts/extract.py --work "$WORK"

# 2. 生成中文词条
#    默认连本机的 OpenAI 兼容服务，llama.cpp / Ollama 都可以
export OPENAI_BASE_URL=http://127.0.0.1:8080/v1
export TRANSLATE_MODEL=local
export TRANSLATE_WORKERS=8
python3 scripts/run_translate.py --work "$WORK"

# 3. 生成打好补丁的归档
python3 scripts/build.py --work "$WORK"

# 4. 安装（需要 sudo，会自动备份原文件）
./scripts/apply.sh --work "$WORK"
```

装完重启 Claude Desktop，设置里的语言列表就能看到「中文（简体）」。

第 2 步可以换成任何 OpenAI 兼容的服务，比如：

```bash
export OPENAI_BASE_URL=https://api.siliconflow.cn/v1
export OPENAI_API_KEY=sk-...
export TRANSLATE_MODEL=Qwen/Qwen2.5-7B-Instruct
```

翻译会写进 `$WORK/cache.jsonl`，中途停掉再跑会接着上次的进度，不会重翻。

## 还原

```bash
./scripts/restore.sh
```

脚本会从 `*.orig-<版本号>` 备份恢复两个 asar。

apt 升级 Claude Desktop 之后补丁会被覆盖，重新执行 `extract.py`、`build.py`、`apply.sh`
就行，已翻译的词条会从缓存里复用，只翻新增的部分。

## 注意

- 翻译由本机模型批量生成，不是完整汉化。长句或 ICU 复数句如果译文破坏了占位符和花括号，会被校验逻辑拦下并保留英文，这部分大约占 6%。
- 应用升级后如果代码里的锚点变了，`build.py` 会直接报错退出，不会生成半成品包。
- 只在 Linux .deb 5.11492.5 上测试过。macOS 和 Windows 的归档结构不同，思路一样，脚本需要另做适配。
- 修改的是本机安装文件，官方不支持。请自行评估风险，不要分发由官方文案衍生的词条文件。

## License

MIT，只覆盖仓库里的脚本。Claude 和 Claude Desktop 是 Anthropic PBC 的商标和版权作品，本项目与其无关。
