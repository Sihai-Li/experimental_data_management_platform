# 神经元 recording 文件数据契约 v1

状态：用户确认的业务规则与首版实现约定。本文优先于旧规划中的 CSV、合成传感器和覆盖式版本流程。仅定义文件导入，不定义科学分析。

## 1. 范围与身份

- 一份文件代表一个 recording session 中的一个神经元。
- animal 缩写为文件名前三个字母；紧随的三位数字为该 animal 的 session 序号。
- neuron_number 在整个实验室全局唯一。
- 仅处理 session 标识后独立 token 为 `1` 的文件；其他编号返回 SKIPPED_UNSUPPORTED_VARIANT，不写业务表，不推测其含义。
- 原始文件不可覆盖；重复内容或重复神经元编号拒绝。特殊重新编号需要文件内部编号、original_file_name、save_file_name 和外部文件名一致更新。

示例：`ADR001_1_3000_SPATIAL_PRE_dorsal_raster_data.mat`。
首版解析前三段为 `ADR001`、`1`、`3000`；剩余名称通过内部字段重新构造后与完整文件名核对，避免盲目按固定 token 数解析名称。
实现约定：三个字母保持原大小写，不静默转换；session 序号解析成整数，同时保留原文件名中的零填充文本。不额外推断序号必须从 1 开始。

## 2. 字段字典与验证

| 源路径 | 类型/形状 | 含义及规则 |
|---|---|---|
| raster_data | 数值矩阵 N × 6001 | trial × 时间点；仅 0/1；0 无放电、1 一次 spike；1 ms 分辨率 |
| raster_labels.stimulus_position_names | N 个字符串 | 第一个视觉刺激的屏幕位置 |
| raster_labels.second_stimulus_position_names | N 个字符串 | 第二个视觉刺激的屏幕位置 |
| raster_labels.is_match_trial | N 个数值 0/1 | 两位置相等当且仅当值为 1 |
| raster_site_info.original_file_name | 非空字符串 | 如 ADR001_1_3000；与外部文件名前三段一致 |
| raster_site_info.save_file_name | 非空字符串 | 与外部文件名去掉 .mat 后完全一致 |
| raster_site_info.neuron_number | 有限、整数值数值标量 | 与文件名编号一致，实验室全局唯一 |
| raster_site_info.experiment_type_name | 非空字符串 | 原样保存，不限定为 SPATIAL |
| raster_site_info.experiment_type | 有限、整数值数值标量 | 原样保存，不推测完整编码表 |
| raster_site_info.training_phase_name | 非空字符串 | 原样保存，不限定为 PRE |
| raster_site_info.training_phase_number | 有限、整数值数值标量 | 原样保存 |
| raster_site_info.brain_area_name | 非空字符串 | 原样保存，不仅限于已观察的两个脑区 |
| raster_site_info.brain_area_number | 有限、整数值数值标量 | 原样保存 |
| raster_site_info.timing_info.cue_sample_interval_length | N 个实数 | 含义、单位未确认；原样保存，不添加正负或范围限制 |
| raster_site_info.timing_info.cue_reward_interval_length | N 个实数 | 含义、单位未确认；原样保存，不添加正负或范围限制 |

九种合法位置：upper_left、upper_center、upper_right、middle_left、middle_center、middle_right、lower_left、lower_center、lower_right。

实现约定：N 必须大于 0；单 trial 仍保留二维 raster。标签/时间允许 MATLAB 行向量或列向量，按元素顺序映射成 N 个 trial，不接受一般二维矩阵冒充向量。时间字段中的非有限值不静默修正：报告警告并保留，读回比较显式处理 NaN 与无穷值。当前三个样例中没有这类值。

名称与编码配对先按文件保存，已观察 SPATIAL/1、PRE/1、dorsal/1、ventral/2；尚未确认完整枚举，不硬编码为封闭字典。新增未知字段保留于原文件，报告 UNMAPPED_FIELD 警告，明确其尚未映射为数据库查询字段。

## 3. 时间与一致性

- 6001 个时间点，首尾相隔 6000 ms；不创建绝对采集时间或事件对齐时间。
- trial_index 为原始行号，从 1 开始。禁止排序、去重 trial、插值、四舍五入或自动修正标签。
- 原文件保留字节一致性；数据库字段保留语义值与对应顺序。MATLAB 包装结构、原 dtype 和数组方向仍可从原文件恢复。
- Raster 保存于原 MAT 文件，不将每一个 0/1 展开为关系表行；通过 source_file 与 trial_index 定位矩阵行。
- 正式成功前读回每个已映射字段、矩阵、原文件校验和并核对；不以行数相同替代内容比较。

## 4. 去重与失败契约

| 情况 | 结果 |
|---|---|
| 不支持的文件名 variant | SKIPPED_UNSUPPORTED_VARIANT |
| 文件无法解析/不支持 MAT 编码 | INVALID_FILE / UNSUPPORTED_MAT_FORMAT |
| 缺字段、类型或形状错误 | INVALID_STRUCTURE，附字段路径 |
| 文件名与内部身份或名称冲突 | IDENTITY_MISMATCH |
| 非 0/1 raster、未知位置、match 不一致 | INVALID_VALUE，附 trial_index，适用时附列号 |
| SHA-256 已存在 | DUPLICATE_FILE，不创建业务记录 |
| neuron_number 已存在 | DUPLICATE_NEURON，不覆盖旧记录 |
| 存储/数据库/读回核对失败 | FAILED，业务事务回滚；保留导入诊断 |

SHA-256 检测字节相同的文件，包括仅改名的文件。重新编码的 MAT 即使哈希改变，仍由神经元唯一约束阻止重复编号；不按 raster 内容相同就认定为同一神经元。
报告包含 contract_version、parser_version、状态、文件名、SHA-256、提取身份、trial_count、issues；每个 issue 包含 code、severity、field_path、可选 trial_index/column_index 和说明。

## 5. 已检查的三个样例

| 文件标识 | N | 列数 | match / non-match | raster 中 1 的数量 |
|---|---:|---:|---|---:|
| ADR001_1_3000 | 108 | 6001 | 54 / 54 | 44 |
| ADR004_1_3007 | 180 | 6001 | 90 / 90 | 370 |
| ELV003_1_1004 | 144 | 6001 | 72 / 72 | 4687 |

432 个 trial 的标签全部一致；三个文件的标签与时间数组长度均匹配。以上为此前只读检查证据，不代表导入代码或数据库测试已经完成。

## 6. 后续实施前事项

- P02 解析器支持 MATLAB level-5（v5/v6/v7–7.2，含压缩），拒绝 v4/v7.3；文件上限 32 MiB，展开元素总量上限 256 MiB，raster 上限 1200 万元素。公开上传前另加进程隔离/超时，不声称已支持所有 MAT 文件。
- 不确定的时间字段含义不阻塞导入。
- 真实样例作为本地验收夹具；不自动发布、提交到公共代码仓库或上传外部服务。
