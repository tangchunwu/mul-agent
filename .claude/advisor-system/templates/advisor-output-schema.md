# 顾问输出协议

每位顾问必须按下面结构输出。

## 推荐字段

```json
{
  "advisor_id": "jobs",
  "advisor_name": "史蒂夫·乔布斯",
  "problem_reframe": "这个问题在我看来真正是什么问题",
  "core_judgment": "一句话核心判断",
  "decision_mode": "focus|cut|build|wait|invest|redesign|simplify|integrate",
  "recommended_actions": [
    "动作1",
    "动作2",
    "动作3"
  ],
  "what_to_cut": [
    "应该停止、删除或避免的东西1",
    "应该停止、删除或避免的东西2"
  ],
  "non_negotiables": [
    "不可妥协条件1",
    "不可妥协条件2"
  ],
  "supporting_logic": [
    "支撑逻辑1",
    "支撑逻辑2",
    "支撑逻辑3"
  ],
  "key_risks": [
    "关键风险1",
    "关键风险2"
  ],
  "assumptions": [
    "关键假设1",
    "关键假设2"
  ],
  "open_questions": [
    "还需要确认的问题1",
    "还需要确认的问题2"
  ],
  "success_metrics": [
    "判断是否成功的指标1",
    "判断是否成功的指标2"
  ],
  "confidence": 0.78,
  "limits": [
    "这种视角容易失效的条件1",
    "这种视角容易失效的条件2"
  ]
}
```

## 字段说明

- `problem_reframe`
  - 顾问如何重写这个问题
- `core_judgment`
  - 顾问最核心的一句话判断
- `decision_mode`
  - 当前顾问建议的主要动作模式
- `recommended_actions`
  - 最多 3 条，必须可执行
- `what_to_cut`
  - 当前顾问认为最该停止、删除或回避的东西
- `non_negotiables`
  - 不满足就不建议继续推进的前提
- `confidence`
  - 0 到 1
- `limits`
  - 明确当前顾问视角的失效边界

## 输出质量要求

- 不空泛
- 不写散文
- 不超过 3 条核心动作
- 必须包含风险、假设和边界
