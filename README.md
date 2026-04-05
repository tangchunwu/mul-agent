# mul-agent

六大师多顾问决策系统。

当前仓库已经初始化完成以下内容：

- 6 位大师顾问 skill
  - 彼得·德鲁克
  - 史蒂夫·乔布斯
  - 原研哉
  - 查理·芒格
  - 沃伦·巴菲特
  - 埃隆·马斯克
- 多顾问系统骨架
  - 总控层 prompt
  - 顾问层 prompt
  - 仲裁层 prompt
  - 统一请求模板
  - 顾问输出协议
  - 最终报告模板
  - 最小可执行 CLI

## 目录

```text
.claude/
├── advisor-system/
│   ├── README.md
│   ├── cli.py
│   ├── advisors.yaml
│   ├── prompts/
│   ├── runtime/
│   ├── templates/
│   └── examples/
└── skills/
    ├── peter-drucker-perspective/
    ├── steve-jobs-perspective/
    ├── kenya-hara-perspective/
    ├── charlie-munger-perspective/
    ├── warren-buffett-perspective/
    └── elon-musk-perspective/
```

## 从哪里开始

先看：

- [.claude/advisor-system/README.md](/E:/mul-agent/.claude/advisor-system/README.md)

再运行：

```bash
set OPENAI_API_KEY=你的密钥
python .claude/advisor-system/cli.py init-request --output .claude/advisor-system/runs/my-request.json
python .claude/advisor-system/cli.py run-all --input .claude/advisor-system/runs/my-request.json --run-dir .claude/advisor-system/runs/my-run
```

## 当前状态

- 仓库已完成初始化
- 已有真实模型调用层
- 可以并行调用顾问并自动生成最终报告
