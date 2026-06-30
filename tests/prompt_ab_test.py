#!/usr/bin/env python3
"""Prompt 策略 A/B 测试 — 因果分类精准率优化

目标：保持召回率100%，提升精确率
当前基线：mimo-v2.5-pro, 精确率78%, 召回率100%, F1=0.88
"""
import json
import os
import sys
import time
import urllib.request
from typing import Dict, List, Tuple, Any

# ── 配置 ──────────────────────────────────────────────────
# 从 openclaw.json 自动读取 API 配置
def _load_api_config():
    import json as _json
    oc_path = os.path.expanduser("~/.openclaw/openclaw.json")
    url = ""
    key = ""
    if os.path.exists(oc_path):
        with open(oc_path) as f:
            oc = _json.load(f)
        providers = oc.get("models", {}).get("providers", {})
        for name, prov in providers.items():
            if prov.get("baseUrl"):
                url = prov["baseUrl"]
            if prov.get("apiKey"):
                key = prov["apiKey"]
            if url and key:
                break
    return url, key

_auto_url, _auto_key = _load_api_config()
API_URL = os.environ.get("CHRONOVISOR_API_URL", _auto_url)
API_KEY = os.environ.get("CHRONOVISOR_API_KEY", _auto_key)
API_MODEL = os.environ.get("CHRONOVISOR_MODEL", "mimo-v2.5-pro")
TEST_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "test_cases_50.json")
TEMPERATURE = 0.1
MAX_TOKENS = 256

# ── 加载测试数据 ──────────────────────────────────────────
def load_test_cases(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ── Prompt 策略定义 ───────────────────────────────────────

def prompt_v1_baseline(cause: str, effect: str) -> str:
    """V1: 基线 — 当前使用的简单 prompt"""
    return f"""判断以下两个事件是否存在因果关系。

事件A（因）：{cause}
事件B（果）：{effect}

只返回JSON，不要其他文字：
{{"is_causal": true/false, "confidence": 0.0-1.0, "reason": "一句话解释"}}"""


def prompt_v2_structured(cause: str, effect: str) -> str:
    """V2: 结构化 — 加入判断维度提示"""
    return f"""你是金融因果分析专家。判断事件A是否是事件B的原因。

事件A（因）：{cause}
事件B（果）：{effect}

请从以下维度分析：
1. 时间顺序：A是否在B之前发生？
2. 传导机制：是否存在合理的因果路径？
3. 领域关联：A和B是否在同一领域或有跨领域传导？
4. 必要性：没有A，B是否仍可能发生？

只返回JSON，不要其他文字：
{{"is_causal": true/false, "confidence": 0.0-1.0, "reason": "一句话解释"}}"""


def prompt_v3_few_shot(cause: str, effect: str) -> str:
    """V3: Few-shot — 给正反例"""
    return f"""你是金融因果分析专家。判断事件A是否是事件B的原因。

示例：
---
事件A：美联储宣布加息25基点
事件B：美股三大指数下跌
→ 是因果关系。加息导致流动性收紧，风险资产承压。
---
事件A：特斯拉发布新车型
事件B：苹果公司股价上涨
→ 不是因果关系。两家公司业务无直接传导机制。
---

现在判断：
事件A（因）：{cause}
事件B（果）：{effect}

只返回JSON，不要其他文字：
{{"is_causal": true/false, "confidence": 0.0-1.0, "reason": "一句话解释"}}"""


def prompt_v4_negative_bias(cause: str, effect: str) -> str:
    """V4: 负面偏置 — 强调"相关≠因果"，降低误判"""
    return f"""你是金融因果分析专家。判断事件A是否是事件B的原因。

⚠️ 重要提醒：
- 相关性不等于因果性
- 只有存在明确传导机制时才判定为因果
- 如果A和B只是同一时期发生但无直接传导，返回 false
- 如果A和B只是同一领域但无因果链，返回 false
- 宁可漏判（false），不要误判（true）

事件A（因）：{cause}
事件B（果）：{effect}

只返回JSON，不要其他文字：
{{"is_causal": true/false, "confidence": 0.0-1.0, "reason": "一句话解释"}}"""


def prompt_v5_mechanism_required(cause: str, effect: str) -> str:
    """V5: 机制必填 — 要求写出传导链，写不出就判 false"""
    return f"""你是金融因果分析专家。判断事件A是否是事件B的原因。

规则：
1. 必须能写出完整的传导机制链（A→...→B），否则判 false
2. 传导机制必须具体，不能是笼统的"影响市场情绪"
3. 如果传导链超过3个中间环节，判为间接因果（confidence < 0.5）
4. 只有同领域直接传导才给高置信度

事件A（因）：{cause}
事件B（果）：{effect}

先写出传导机制链，再判断因果关系。

只返回JSON，不要其他文字：
{{"is_causal": true/false, "confidence": 0.0-1.0, "reason": "一句话解释", "mechanism": "A→X→Y→B"}}"""


def prompt_v6_two_stage(cause: str, effect: str) -> str:
    """V6: 两阶段 — 先判断相关性，再判断因果性"""
    return f"""你是金融因果分析专家。

事件A（因）：{cause}
事件B（果）：{effect}

分两步思考：
第一步：A和B是否相关？（同领域/有传导可能）
第二步：如果相关，A是否是B的直接原因？（有明确传导机制）

只有两步都通过才判定为因果。

只返回JSON，不要其他文字：
{{"is_causal": true/false, "confidence": 0.0-1.0, "reason": "一句话解释"}}"""


def prompt_v7_confidence_threshold(cause: str, effect: str) -> str:
    """V7: 高阈值 — 只有高置信度才判 true"""
    return f"""你是金融因果分析专家。判断事件A是否是事件B的原因。

判断标准（从严）：
- 必须有明确的经济/金融传导机制
- 传导机制必须是常识性的、可验证的
- 如果你不确定，返回 false
- 只有 confidence >= 0.8 才判 is_causal=true

事件A（因）：{cause}
事件B（果）：{effect}

只返回JSON，不要其他文字：
{{"is_causal": true/false, "confidence": 0.0-1.0, "reason": "一句话解释"}}"""


PROMPT_STRATEGIES = {
    "V1_baseline": prompt_v1_baseline,
    "V2_structured": prompt_v2_structured,
    "V3_few_shot": prompt_v3_few_shot,
    "V4_negative_bias": prompt_v4_negative_bias,
    "V5_mechanism_required": prompt_v5_mechanism_required,
    "V6_two_stage": prompt_v6_two_stage,
    "V7_confidence_threshold": prompt_v7_confidence_threshold,
}

# ── API 调用 ──────────────────────────────────────────────

def call_api(prompt: str) -> Dict[str, Any]:
    """调用 mimo API"""
    base = API_URL.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"

    payload = json.dumps({
        "model": API_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }).encode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        if not content and msg.get("reasoning_content"):
            content = msg["reasoning_content"]
        return extract_json(content)


def extract_json(text: str) -> Dict[str, Any]:
    """从 LLM 输出中提取 JSON"""
    import re
    # 先找代码块里的 JSON
    match = re.search(r'```json\s*(.+?)\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 找 JSON 对象
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


# ── 评估逻辑 ──────────────────────────────────────────────

def evaluate_strategy(
    strategy_name: str,
    prompt_fn,
    test_cases: List[Dict],
    confidence_threshold: float = 0.5,
) -> Dict[str, Any]:
    """评估单个策略"""
    tp = fp = tn = fn = 0
    details = []

    for case in test_cases:
        cause = case["cause"]
        effect = case["effect"]
        expected = case["expected"]

        prompt = prompt_fn(cause, effect)
        try:
            result = call_api(prompt)
        except Exception as e:
            print(f"  [ERROR] {case['id']}: {e}", file=sys.stderr)
            continue

        # 提取预测结果
        is_causal = result.get("is_causal", False)
        confidence = result.get("confidence", 0.0)
        reason = result.get("reason", "")

        # 对 V7 策略，应用高阈值
        if strategy_name == "V7_confidence_threshold" and confidence < 0.8:
            is_causal = False

        predicted = bool(is_causal)

        # 统计
        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and not expected:
            tn += 1
        else:  # not predicted and expected
            fn += 1

        correct = predicted == expected
        details.append({
            "id": case["id"],
            "cause": cause[:30] + "..." if len(cause) > 30 else cause,
            "effect": effect[:30] + "..." if len(effect) > 30 else effect,
            "expected": expected,
            "predicted": predicted,
            "confidence": confidence,
            "correct": correct,
            "category": case.get("category", ""),
            "reason": reason[:50] if reason else "",
        })

        # 节流
        time.sleep(0.3)

    # 计算指标
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "strategy": strategy_name,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "total": len(test_cases),
        "details": details,
    }


# ── 主流程 ────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("因果分类 Prompt 策略 A/B 测试")
    print(f"模型: {API_MODEL}")
    print(f"温度: {TEMPERATURE}")
    print("=" * 60)

    test_cases = load_test_cases(TEST_FILE)
    print(f"测试用例: {len(test_cases)} 条 (正例: {sum(1 for c in test_cases if c['expected'])}, 负例: {sum(1 for c in test_cases if not c['expected'])})")
    print()

    all_results = []

    for name, fn in PROMPT_STRATEGIES.items():
        print(f"▶ 测试策略: {name}")
        result = evaluate_strategy(name, fn, test_cases)
        all_results.append(result)

        # 打印错误案例
        errors = [d for d in result["details"] if not d["correct"]]
        fp_cases = [d for d in errors if d["predicted"] and not d["expected"]]
        fn_cases = [d for d in errors if not d["predicted"] and d["expected"]]

        print(f"  精确率: {result['precision']:.1%}  召回率: {result['recall']:.1%}  F1: {result['f1']:.2f}")
        print(f"  TP={result['tp']} FP={result['fp']} TN={result['tn']} FN={result['fn']}")
        if fp_cases:
            print(f"  误判({len(fp_cases)}):")
            for c in fp_cases[:3]:
                print(f"    ✗ {c['cause']} → {c['effect']} (conf={c['confidence']:.2f})")
        if fn_cases:
            print(f"  漏判({len(fn_cases)}):")
            for c in fn_cases[:3]:
                print(f"    ✗ {c['cause']} → {c['effect']} (conf={c['confidence']:.2f})")
        print()

    # ── 汇总对比 ──────────────────────────────────────────
    print("=" * 60)
    print("策略对比汇总")
    print("=" * 60)
    print(f"{'策略':<25} {'精确率':>8} {'召回率':>8} {'F1':>8} {'误判':>4} {'漏判':>4}")
    print("-" * 60)
    for r in all_results:
        recall_flag = " ✓" if r["recall"] == 1.0 else " ✗"
        print(f"{r['strategy']:<25} {r['precision']:>7.1%} {r['recall']:>7.1%}{recall_flag} {r['f1']:>7.2f} {r['fp']:>4} {r['fn']:>4}")

    # 找最优：召回率100%的前提下精确率最高
    perfect_recall = [r for r in all_results if r["recall"] == 1.0]
    if perfect_recall:
        best = max(perfect_recall, key=lambda r: r["precision"])
        print(f"\n🏆 最优策略（召回率100%）: {best['strategy']}")
        print(f"   精确率: {best['precision']:.1%}, F1: {best['f1']:.2f}")
    else:
        print("\n⚠️ 没有策略达到100%召回率")

    # 保存详细结果
    output_file = os.path.join(os.path.dirname(__file__), "prompt_ab_results.json")
    with open(output_file, "w", encoding="utf-8") as f:
        # 只保存汇总，不保存 details（太大）
        summary = [{k: v for k, v in r.items() if k != "details"} for r in all_results]
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_file}")


if __name__ == "__main__":
    main()
