# Hachi 毕业论文 Typst 工程

本目录基于 `KeithCoreDumped/bupt-typst` 模板整理，模板来源：

- 仓库：`https://github.com/KeithCoreDumped/bupt-typst`
- 当前核对的上游提交：`2af56c9e5fc4d2ddc174525d9198f7df6cd352f6 fix heading refs`

## 文件说明

- `main.typ`：论文正文初稿，已按当前 Hachi 项目重写标题、摘要、章节和图表。
- `template.typ`：BUPT Typst 模板文件；已基于上游最新版调整分页策略以去除空白页。
- `reference.bib`：论文参考文献。
- `gb-t-7714-2015-numeric.csl`、`numeric-inline.csl`：参考文献样式文件。
- `images/`：论文图示，目前包括系统架构、RAG 问答流程和 Chrome 插件数据流。
- `LICENSE.bupt-typst`：上游模板许可证副本。
- `additional/forms/`：从 `QQKdeGit/bupt-typst` v1.2.0 release 的 `addition.zip` 解压出的缺失 Word 模板，包括封面、诚信声明/论文使用授权、任务书、成绩评定表、开题报告、中期检查表、教师指导记录表等。
- `fonts/`：从 `QQKdeGit/bupt-typst` v1.2.0 release 的 `fonts.zip` 解压出的字体文件，目录较大，已在 `.gitignore` 中忽略。

## 编译方式

在另一台电脑上重新编译时，先从仓库根目录创建虚拟环境并安装本目录锁定的 Typst Python 包：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r doc/thesis/requirements.txt
```

然后执行：

```bash
python doc/thesis/build_thesis.py
```

脚本会在 `doc/thesis/` 下生成 `Hachi-Thesis.pdf`。PDF 是生成文件，不需要提交到 Git。

该模板依赖宋体、黑体、楷体、Times New Roman 等字体。若本地字体缺失，可安装系统字体，或从 `QQKdeGit/bupt-typst` v1.2.0 release 下载 `fonts.zip` 并解压到 `doc/thesis/fonts/fonts`。也可以显式传入字体目录：

```bash
python doc/thesis/build_thesis.py --font-path /path/to/fonts
```

首次编译时需要联网下载 `@preview` 模板依赖包，后续会使用本地 Typst 缓存。

已根据 README 中关于“神奇空页”的说明调整本地 `template.typ`：将强制奇数页的 `pagebreak(to: "odd", weak: true)` 改为普通 `pagebreak(weak: true)`，并移除了模板末尾额外补空页的逻辑。当前已成功编译生成 `Hachi-Thesis.pdf`，PDF 共 31 页，脚本检查未发现空白页。PDF 属于生成文件，已在 `.gitignore` 中忽略。

## 完整装订顺序

根据 `bupt-typst` README，完整论文装订顺序建议为：

封面 → 诚信声明，关于论文使用授权的说明（一页） → 任务书 → 成绩评定表 → 论文正文 → 开题报告 → 中期进展情况检查表 → 教师指导毕业设计(论文)记录表 → 提前毕设审批表（如有） → 论文题目变更申请表（如有） → 变更指导教师申请表（如有）。

其中 `Hachi-Thesis.pdf` 只对应“论文正文”部分；前后 Word 表格需按学院要求填写并导出 PDF 后拼接。

## 后续需要你补充的内容

- 封面、诚信声明、任务书等 Word 部分仍按学院模板单独处理，`bupt-typst` 主要负责论文正文部分。
- 第五章测试数据当前写入的是当前项目已有自动化测试结果，后续可以补充真实问答样例、截图和性能记录。
- 致谢、攻读学位期间成果等部分现在是占位文本，提交前需要改成你的真实内容。
