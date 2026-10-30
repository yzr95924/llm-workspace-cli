---
title: "Attention 论文学习笔记"
description: "Attention Is All You Need 的合成转述笔记"
type: source
tags: [model, architecture, paper]
created: 2026-10-24 22:05
updated: 2026-10-24 22:05
sources:
  - raw/articles/attention.md
---

# Attention 论文学习笔记

**作者**：合成夹具（转述 Vaswani et al. 的论文笔记）
**来源**：[raw/articles/attention.md](../../raw/articles/attention.md)

## 摘要

对 Transformer 论文的转述笔记：完全基于注意力，任意位置直接交互；
承认平方复杂度，但主张在典型序列长度下不构成瓶颈。

## 关键贡献

1. 缩放点积注意力与多头机制。
2. 用位置编码替代循环结构。

## 关键数字 / 实验结果

- 机器翻译超过当时最好的循环序列模型，训练时间显著更短。

## 与本 wiki 其它资料的关系

- 概念页见 [Transformer](../concepts/transformer.md)
- 与 [Mamba 论文学习笔记](../sources/mamba-notes.md) 立场冲突：本页认为平方
  开销可被并行度弥补，Mamba 侧认为注意力路线在超长序列上不可持续

## 参考来源 / Sources

- [raw/articles/attention.md](../../raw/articles/attention.md)
