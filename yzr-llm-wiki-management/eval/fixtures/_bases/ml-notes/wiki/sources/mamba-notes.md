---
title: "Mamba 论文学习笔记"
description: "Mamba 论文的合成转述笔记"
type: source
tags: [model, architecture, paper]
created: 2026-10-24 21:54
updated: 2026-10-24 21:54
sources:
  - raw/articles/mamba.md
---

# Mamba 论文学习笔记

**作者**：合成夹具（转述 Albert Gu 与 Tri Dao 的论文笔记）
**来源**：[raw/articles/mamba.md](../../raw/articles/mamba.md)

## 摘要

对 Mamba（选择性状态空间模型）的转述笔记：主张注意力不是长序列建模的
必需品，SSM 以线性时间即可顶替注意力做通用骨干，序列越长优势越大。

## 关键贡献

1. 选择性状态空间机制：让 SSM 参数随输入变化，恢复内容过滤能力。
2. 硬件感知并行扫描：把状态递推组织成贴合 GPU 内存层级的 kernel。

## 关键数字 / 实验结果

- 语言建模与基因组等长序列任务上，小尺寸 Mamba 追平或超过同规模 Transformer。

## 与本 wiki 其它资料的关系

- 概念页见 [Mamba](../concepts/mamba.md)
- 与 [Transformer](../concepts/transformer.md) 页的立场冲突：本页一侧认为
  平方复杂度使注意力路线在长序列上不可持续，Transformer 页认为平方开销
  在典型长度下不构成瓶颈
