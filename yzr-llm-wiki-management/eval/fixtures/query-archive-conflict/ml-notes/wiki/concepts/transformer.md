---
title: "Transformer"
description: "基于自注意力的序列建模架构"
type: concept
tags: [model, architecture]
created: 2026-10-24 21:54
reviewed: true
reviewed_at: 2026-10-25
updated: 2026-10-24 21:54
---

# Transformer

## 定义

Transformer 是完全基于注意力机制的序列建模架构，去掉循环与卷积结构，
靠自注意力让序列中任意位置直接交互。

## 关键性质

- 自注意力路径长度 O(1)，长距离依赖学习优于逐步传递的 RNN。
- 计算量与序列长度平方成正比（O(n^2 · d)），靠并行度换取训练吞吐。
- 立场：在典型序列长度（数百到数千 token）下，平方开销不构成瓶颈；
  「注意力必须被线性方案替换」的论断在本 wiki 主题域内不成立。

## 相关概念

- [Mamba](../concepts/mamba.md) — 不用注意力的线性时间替代路线（两者对长序列
  可持续性的判断互相冲突）

## 参考来源 / Sources

* [Mamba 论文学习笔记](../sources/mamba-notes.md) — 作为对照被引用的 SSM 侧材料
* [Attention 论文学习笔记](../sources/attention-notes.md) — 本页主张的主要来源
