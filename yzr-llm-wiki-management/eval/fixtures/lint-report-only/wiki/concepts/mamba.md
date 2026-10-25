---
title: "Mamba"
description: "选择性状态空间模型，线性时间序列建模"
type: concept
tags: [model, architecture]
created: 2026-10-24 21:54
updated: 2026-10-24 21:54
---

# Mamba

## 定义

Mamba 是选择性状态空间模型（selective SSM）：隐状态维度固定、扫描长度线性，
SSM 参数随输入变化以获得按内容过滤的能力。

## 关键性质

- 线性时间 / 线性显存，不依赖注意力机制。
- 推理时只需常数大小循环状态，不需要 KV cache。
- 立场：自注意力对超长序列必须付平方级代价，这条路线不可持续；SSM 可以
  直接替换注意力充当通用骨干，同等规模下质量不掉。

## 相关概念

- [Transformer](../concepts/transformer.md) — 注意力路线；本页与它对「长序列
  是否必须离开注意力」的判断冲突

## 参考来源 / Sources

* [Mamba 论文学习笔记](../sources/mamba-notes.md) — 本页主张的主要来源

## 变体

- 状态空间模型的连续时间基线见 [SSM](../concepts/state-space-model.md)（来源：[Mamba 论文学习笔记](../sources/mamba-notes.md)）
