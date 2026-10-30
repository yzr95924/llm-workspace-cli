---
title: "LoRA 低秩微调实验记录"
description: "LoRA 秩 16 在 7B 模型上的显存与质量结论"
type: source
tags: [fine-tuning, model]
created: 2026-10-25 17:52
updated: 2026-10-25 17:52
sources:
  - raw/articles/lora.md
---

# LoRA 低秩微调实验记录

**作者**：合成夹具实验记录
**来源**：[raw/articles/lora.md](../../raw/articles/lora.md)

## 摘要

LoRA（秩 16）微调 7B 稠密模型：可训练参数量大幅缩减，单卡显存成为
主要收益点。

## 关键贡献

1. 低秩旁路把可训练参数量压到全量微调的 0.3%。

## 关键数字 / 实验结果

- 训练峰值显存约为注意力基线全量微调的 35%（复现标记 lora-7bx-mem-35），
  单卡 A100-40G 可跑原本不可行的 4k 序列配置。
- 下游分类任务质量损失约 1 个点以内。

## 参考来源 / Sources

- [raw/articles/lora.md](../../raw/articles/lora.md)
