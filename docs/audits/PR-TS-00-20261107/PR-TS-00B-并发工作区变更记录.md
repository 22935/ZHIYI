# PR-TS-00B｜结束前并发工作区变更

VERIFIED：本轮开始时tracked/staged为空，只有原PR-TS-00审计目录未跟踪。第一次打包校验时，`git diff --name-only`发现以下4个tracked删除，HEAD仍为`8775130f22b0440398c876a99206a47054e0b30c`：

- `benchmark/agentos_benchmark_smoke.py`
- `benchmark/agentos_benchmark_smoke_6.py`
- `ops/scripts/generate_agentos_acg_master_drawio.py`
- `ops/scripts/generate_harness_report.py`

删除合计2812行；staged为空。这些文件不属于本轮写入路径，本轮脚本没有删除或恢复它们；变更来源未归因，完整保留。第一次打包因“tracked应为空”的防护断言退出，未产生ZIP，不视为数据查询失败。

审计引用的源码索引和上一轮产物SHA-256仍全部一致，所以本轮业务合同依据未漂移。最终打包只允许这组已观测的无关删除保持原状；若审计源文件、HEAD或其他路径再次变化，校验会停止。

本文件补充此前报告中的“开始/生成报告时tracked为空”观察：**结束时工作区为Dirty（4个tracked删除+审计目录未跟踪），不得报告为全工作区干净**。本轮新增内容仍只在审计目录、E盘隔离产物和桌面交付包；无stage/commit/push。
