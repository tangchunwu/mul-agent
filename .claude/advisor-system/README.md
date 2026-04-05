# 六大师多顾问决策机制

这套骨架把 6 个已蒸馏完成的 perspective skill 组织成一个可运行的多顾问系统。

目标不是做“名人模仿秀”，而是让 6 套不同的决策镜片并行分析同一个问题，再由仲裁层整合成可执行建议。

## 目录结构

```text
.claude/advisor-system/
├── README.md
├── advisors.yaml
├── prompts/
│   ├── orchestrator.md
│   ├── advisor.md
│   └── arbiter.md
└── templates/
    ├── request-template.md
    ├── advisor-output-schema.md
    └── final-report-template.md
```

## 系统分层

### 1. 总控层

- 负责理解问题
- 负责判断是否要启用全部 6 位顾问，还是只启用部分顾问
- 负责把同一份问题包发给各顾问
- 负责把结果送给仲裁层

对应文件：

- `prompts/orchestrator.md`

### 2. 顾问层

- 每位顾问绑定一个 perspective skill
- 每位顾问只从自己的镜片出发分析问题
- 顾问不能为了“达成一致”而主动磨平差异

对应文件：

- `advisors.yaml`
- `prompts/advisor.md`
- 已完成的 6 个 `*-perspective` skill

### 3. 仲裁层

- 不做简单平均
- 提取共识
- 保留关键分歧
- 给出条件化建议
- 生成面向执行的最终输出

对应文件：

- `prompts/arbiter.md`
- `templates/final-report-template.md`

### 4. 协议层

- 固定输入字段
- 固定顾问输出结构
- 固定最终报告结构
- 让系统从“会讨论”变成“可编排”

对应文件：

- `templates/request-template.md`
- `templates/advisor-output-schema.md`

## 六位顾问

- `peter-drucker-perspective`
  - 管理、组织设计、目标管理、知识工作者
- `steve-jobs-perspective`
  - 聚焦、产品定义、完整体验、品味门槛
- `kenya-hara-perspective`
  - 感知、留白、信息传达、品牌气候、日常体验
- `charlie-munger-perspective`
  - 多元模型、反向思考、误判心理学、激励结构
- `warren-buffett-perspective`
  - 能力圈、护城河、安全边际、资本配置、长期复利
- `elon-musk-perspective`
  - 第一性原理、工程速度、极限降本、垂直整合

## 推荐工作流

1. 先准备统一的问题包
2. 总控层判断启用哪些顾问
3. 并行运行顾问层
4. 每位顾问按固定协议输出
5. 仲裁层读取全部输出并生成最终报告
6. 如有重大冲突，再跑一轮 challenge round

## 什么时候启用全部 6 位顾问

- 公司级战略
- 新产品方向
- 品牌与商业模式一起变化
- 组织与产品需要同时重构
- 高风险重大投入

## 什么时候只启用部分顾问

- 纯组织问题：
  - 德鲁克、芒格、马斯克
- 纯产品问题：
  - 乔布斯、原研哉、芒格
- 纯投资或资本配置问题：
  - 巴菲特、芒格、德鲁克
- 纯工程和制造问题：
  - 马斯克、乔布斯、德鲁克

## 最小运行示例

### 输入问题

```markdown
我们要不要在未来 12 个月内推出面向中小企业的 AI 协作产品？

背景：
- 当前已有企业服务收入
- 团队 18 人
- 现金还能支撑 14 个月
- 现有产品留存一般
- 品牌认知弱

目标：
- 找到最值得押注的一条增长路径
```

### 系统执行

1. 总控层读取 `request-template.md`
2. 选中 6 位顾问并行分析
3. 每位顾问按 `advisor-output-schema.md` 输出
4. 仲裁层按 `final-report-template.md` 汇总

## CLI 快速开始

### 1. 生成请求模板

```bash
python .claude/advisor-system/cli.py init-request --output .claude/advisor-system/runs/my-request.json
```

### 2. 编辑请求文件

编辑：

- `runs/my-request.json`

### 3. 生成运行包

```bash
python .claude/advisor-system/cli.py prepare-run --input .claude/advisor-system/runs/my-request.json --run-dir .claude/advisor-system/runs/my-run
```

这一步会生成：

- `advisor-prompts/*.md`
- `advisor-outputs/*.json`
- `request.normalized.json`

### 4. 填写顾问输出

把每位顾问的结果写回：

- `advisor-outputs/<advisor>.json`

### 5. 生成仲裁输入

```bash
python .claude/advisor-system/cli.py build-arbiter --run-dir .claude/advisor-system/runs/my-run
```

会生成：

- `artifacts/arbiter-input.json`
- `artifacts/arbiter-prompt.md`

### 6. 查看运行状态

```bash
python .claude/advisor-system/cli.py status --run-dir .claude/advisor-system/runs/my-run
```

## 使用原则

- 顾问层必须保留差异，不得强行共识化
- 仲裁层必须说明“为什么选这个建议，而不是平均意见”
- 涉及当代人物的最新信息，必须重新核验
- 不允许把顾问人格风格当作分析能力的替代品

## 下一步

如果要把这套骨架真正接到 agent 编排器里，建议再补两件事：

1. 一个执行脚本
   - 读取问题包
   - 并行调 6 个顾问
   - 汇总 JSON 输出

2. 一个评测集
   - 10 到 20 个真实决策问题
   - 用来对比单顾问、六顾问、六顾问+仲裁的效果差异
