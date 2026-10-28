"""原因码总表。

三个来源共用一个码表，评测才能横向统计"哪类失败最多"：

    执行失败   浏览器 / 抽取阶段
    核验失败   落库结果和源头对不上
    采信失败   模型没给出能用的结论

码值是字符串常量，落库进 runs.reason_code / verifications.reason_code，
所以**不能随便改**——改了历史数据就对不上。新增可以，重命名要迁移。
"""

from __future__ import annotations

# ---- 执行失败 --------------------------------------------------------- #

STEP_TIMEOUT = "STEP_TIMEOUT"            # 等不到预期状态
TASK_NOT_FOUND = "TASK_NOT_FOUND"        # 任务文件不存在
MISSING_RECIPE = "MISSING_RECIPE"        # 任务没声明配方
RECIPE_NOT_FOUND = "RECIPE_NOT_FOUND"    # 配方文件不存在
RECIPE_NAME_MISMATCH = "RECIPE_NAME_MISMATCH"
MISSING_INPUT = "MISSING_INPUT"          # 配方参数没给全
ACTION_UNSUPPORTED = "ACTION_UNSUPPORTED"
ASSERT_UNSUPPORTED = "ASSERT_UNSUPPORTED"
ASSERT_TEXT_MISMATCH = "ASSERT_TEXT_MISMATCH"
ASSERT_COUNT_MISMATCH = "ASSERT_COUNT_MISMATCH"
ASSERT_NOT_VISIBLE = "ASSERT_NOT_VISIBLE"
ASSERT_NO_TEXT = "ASSERT_NO_TEXT"
EXTRACT_NO_TABLE = "EXTRACT_NO_TABLE"    # 找不到表：可能是漂移，也可能是 in_frame 写错
EXTRACT_NO_HEADER = "EXTRACT_NO_HEADER"
EXTRACT_EMPTY_FORM = "EXTRACT_EMPTY_FORM"
EXTRACT_TRUNCATED = "EXTRACT_TRUNCATED"  # 出现分页：只读到第一页，数据不完整
EXTRACT_NO_TEXT = "EXTRACT_NO_TEXT"      # 该有文本的元素不见了
REPAIR_UNSUPPORTED_PATH = "REPAIR_UNSUPPORTED_PATH"  # 不知道该把新定位写到哪

# ---- 自愈 ------------------------------------------------------------- #

LOCATE_DRIFT_UNREPAIRED = "LOCATE_DRIFT_UNREPAIRED"  # 修过，重试仍然失败

# ---- 核验失败 --------------------------------------------------------- #

REF_MISMATCH = "REF_MISMATCH"            # 外部单号对不上
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"      # 合计对不上
AMOUNT_UNPARSABLE = "AMOUNT_UNPARSABLE"
ROW_COUNT_MISMATCH = "ROW_COUNT_MISMATCH"
DEPT_MISMATCH = "DEPT_MISMATCH"
ATTACHMENT_MISMATCH = "ATTACHMENT_MISMATCH"

# ---- 采信失败 --------------------------------------------------------- #

CLASSIFY_FAILED = "CLASSIFY_FAILED"      # 调用模型失败
CLASSIFY_UNCERTAIN = "CLASSIFY_UNCERTAIN"  # 模型说拿不准
CLASSIFY_LOW_CONFIDENCE = "CLASSIFY_LOW_CONFIDENCE"

# ---- 业务冲突（不是"我们错了"，是"需要人决策"） ---------------------- #

DUPLICATE_DOC = "DUPLICATE_DOC"            # 单号已入账，不能改
MAPPING_MISSING = "MAPPING_MISSING"        # 部门/成本中心映射不到
ACCOUNT_UNRESOLVED = "ACCOUNT_UNRESOLVED"  # 有明细行没定下科目
ATTACHMENT_MANUAL_REVIEW = "ATTACHMENT_MANUAL_REVIEW"  # 附件需要人工核对
VERIFY_MISMATCH = "VERIFY_MISMATCH"        # 落库结果和源头对不上
VALIDATION_UNFIXABLE = "VALIDATION_UNFIXABLE"  # 校验错误修不了
EVIDENCE_MISSING = "EVIDENCE_MISSING"      # 库里没有执行证据


# 哪些码代表"需要人决策"，而不是"我们出错了"。
# 决定任务终态：在集合里 → waiting_human，否则 → failed。
NEEDS_HUMAN = frozenset(
    {
        DUPLICATE_DOC,
        MAPPING_MISSING,
        ACCOUNT_UNRESOLVED,
        ATTACHMENT_MANUAL_REVIEW,
        VERIFY_MISMATCH,
        VALIDATION_UNFIXABLE,
        CLASSIFY_UNCERTAIN,
        CLASSIFY_LOW_CONFIDENCE,
        EXTRACT_TRUNCATED,
    }
)


def needs_human(code: str) -> bool:
    return code in NEEDS_HUMAN


# 失败大类：给评测报表分组用。
# 没有登记的码归到 OTHER，报表里能看出"有没归类的原因码"。
FAILURE_CATEGORY: dict[str, str] = {
    STEP_TIMEOUT: "LOCATE",
    EXTRACT_NO_TABLE: "LOCATE",
    EXTRACT_NO_HEADER: "LOCATE",
    EXTRACT_EMPTY_FORM: "LOCATE",
    EXTRACT_TRUNCATED: "EXTRACT",
    LOCATE_DRIFT_UNREPAIRED: "LOCATE",
    REPAIR_UNSUPPORTED_PATH: "LOCATE",
    ASSERT_TEXT_MISMATCH: "ASSERT",
    ASSERT_COUNT_MISMATCH: "ASSERT",
    ASSERT_NOT_VISIBLE: "ASSERT",
    ASSERT_NO_TEXT: "ASSERT",
    REF_MISMATCH: "DATA",
    AMOUNT_MISMATCH: "DATA",
    AMOUNT_UNPARSABLE: "DATA",
    ROW_COUNT_MISMATCH: "DATA",
    DEPT_MISMATCH: "DATA",
    ATTACHMENT_MISMATCH: "DATA",
    VERIFY_MISMATCH: "DATA",
    CLASSIFY_FAILED: "JUDGMENT",
    CLASSIFY_UNCERTAIN: "JUDGMENT",
    CLASSIFY_LOW_CONFIDENCE: "JUDGMENT",
    ACCOUNT_UNRESOLVED: "JUDGMENT",
    DUPLICATE_DOC: "CONFLICT",
    MAPPING_MISSING: "MAPPING",
    VALIDATION_UNFIXABLE: "VALIDATION",
    ATTACHMENT_MANUAL_REVIEW: "REVIEW",
    EVIDENCE_MISSING: "INTERNAL",
}


def category(code: str | None) -> str:
    """码 → 大类。未登记的返回 OTHER。"""
    if code is None:
        return "OTHER"
    return FAILURE_CATEGORY.get(code, "OTHER")
