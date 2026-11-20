# ArkStory Data

首页读取 `data/<locale>/index.json`，按每张卡片的 `detail` 相对路径读取活动详情。支持 zh_CN、en_US、ja_JP 和 ko_KR。活动详情保留游戏目录顺序、章节编号、战前/战后标签、章节简介及原版 TXT 相对路径。

封面、标题、背景、intro 和 loop 的字段值是 `data/media.json` 中 resources 的键。即使键看起来像 URL，也应通过资源记录的 path 读取本仓库文件。path 相对仓库根目录。sources 由生成器配置管理，文件以 SHA-256 命名。各语言目录共享媒体库，活动主题补充遵循 config/themes.json 中的语言范围。上游没有提供的字段可以为 null。

每天及手动触发 Update ArkStory data。Action 从 Kengxxiao 游戏数据的三个配置表和章节摘要生成各语言目录，只检出摘要目录。国服官方热更新清单提供图片图集和音频包；压缩解码复用固定版本 kawapack 的 LZ4AK 模块，UnityPy 提取图片和音轨。特殊联动使用配置指定的原图或音源。检查包内 MD5、输出文件哈希、图片及音频可读性后一次提交。任务失败时保留上一版发布。

手动复现时按 .github/workflows/update.yml 准备三个稀疏检出目录，安装 requirements.txt，依次运行 catalog.py 和 media.py。游戏原始素材归其权利人所有。
config/archived-media.json 记录当前游戏包中缺失的历史资源。现有归档为《无忧梦呓》的回顾背景，沿用旧版已核验的 SHA-256。外部特例同样在首次导入时校验，后续复用仓库内的媒体；变更来源时重新获取。
