# Leader 任务闭环验收记录

日期：2026-10-15。

## 已验证

- 后端完整回归：`python -m pytest --basetemp output/test-temp/luna-final -ra`，58 passed，106.97 秒。
- 前端类型检查与生产构建通过。
- 隔离浏览器验证：需求提交、反馈重规划、计划差异、扩展审批、工具审批、执行恢复、文件预览与下载、针对产物反馈、显式验收与案例归档。
- 多 Session 切换不串入旧会话数据；桌面与 390px 视口无页面级横向溢出。
- 真实服务浏览器验证：显示模型授权失败详情与重试规划按钮，控制台无 error/warning。
- 后续能力路线完整回归：61 passed，123.19 秒；前端重新构建通过。覆盖空搜索、网络失败、有界搜索、替代方案选择后重规划与审批隔离，以及模型失败时保留选择。
- 隔离浏览器点击路线后，反馈中保留用户选择及“不是执行授权”，新计划仍需批准；390px 无页面级横向溢出。阻塞 Session 在列表显示 blocked 与缺口摘要。

## 真实模型验收

真实前端：`http://127.0.0.1:5174`；真实后端：`http://127.0.0.1:8007`。

配置：`config/examples/local.openai.yaml`，`xingwan-gpt / gpt-5.6-luna`。全部 Agent 使用相同模型，后端确认从用户级环境变量读取到 `XINGWAN_API_KEY`。

旧密钥下，真实 Session `59c470d2-1e92-4fb9-a5f1-5db69f915ff3` 的结构化规划请求及最小 `chat/completions` 请求曾返回 HTTP 403。系统没有切换到模拟模型，并保留了失败状态和重试入口。更换用户级密钥并重启后端后，最小请求返回 HTTP 200。

- 同一 Session 随后完成真实规划、用户纠偏、重规划、审批与执行；`connectivity-check.md` 的实际文件内容为纠偏后要求的 `REAL_MODEL_OK_V2`。
- 真实 Session `0935723e-2cf1-4f29-b004-5c1487ef4e89` 生成恰好两个串行 Action：`story_writer` 写入 `summary.md`，`story_reviewer` 读取该文件后核对 120、45、75 和 November 2，并写入 `review.md`。
- 浏览器刷新后，队列与详情均为 `completed`；协作图显示两个 Agent、六次真实模型调用、文件读写、审批、产物和 Agent 消息；交付页可预览两个 Markdown 文件。控制台 0 error、0 warning。

隔离浏览器仍只用于证明能力缺口和审批边界的确定性交互；真实外部 Skill/MCP 的运行质量尚未因此得到证明。

## 截图

- 桌面：`playwright/leader-cockpit-desktop.png`
- 移动视口：`playwright/leader-cockpit-mobile.png`
- 真实模型授权阻塞：`playwright/leader-real-model-permission.png`
- 真实模型完成：`playwright/leader-real-model-completed.png`
- 能力路线：`playwright/leader-capability-routes.png`、`playwright/leader-capability-routes-mobile.png`

## 未完成边界

真实复合任务的替代路线质量验收、完整 MCP Server 运行时、不可变产物内容快照与追加式恢复、OS/容器沙箱、进化候选自动评估与发布。详细后续方向见项目根目录 `GOAL.md`。
