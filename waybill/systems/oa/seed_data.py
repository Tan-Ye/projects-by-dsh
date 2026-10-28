"""OA 仿真系统的种子数据。

金额一律按「分」存整数，避免浮点误差；渲染时再格式化成 ￥1,286.00元。
"""

USERS = [
    {"username": "zhangwei", "password": "oa123456", "display_name": "张伟", "department": "市场部"},
    {"username": "lina", "password": "oa123456", "display_name": "李娜", "department": "销售部"},
]

# 每张单据：
#   doc_no / applicant / department / reason / submitted_at / status
#   lines: (occurred_on, description, amount_cents, attachment_count)
#   attachments: (line_seq, filename)  —— line_seq=0 表示没有挂到任何明细行上的孤立附件
DOCS = [
    # ---- 四个任务单据 ----------------------------------------------------
    {
        "doc_no": "BX-2024-0912",
        "applicant": "张伟",
        "department": "市场部",
        "reason": "客户拜访交通费",
        "submitted_at": "2024-09-10 18:22",
        "status": "approved",
        "lines": [
            ("2024-09-10", "客户拜访打车费", 12860, 1),
        ],
        "attachments": [(1, "出租车发票_0910.pdf")],
    },
    {
        "doc_no": "BX-2024-0930",
        "applicant": "李娜",
        "department": "销售部",
        "reason": "北京客户现场支持差旅",
        "submitted_at": "2024-09-30 20:05",
        "status": "approved",
        "lines": [
            ("2024-09-26", "北京出差住宿费（2 晚）", 88000, 1),
            ("2024-09-27", "客户招待用餐", 26000, 1),
            ("2024-09-28", "北京往返高铁票", 55300, 1),
        ],
        "attachments": [
            (1, "住宿费发票_0926.pdf"),
            (2, "餐饮发票_0927.pdf"),
            (3, "高铁票_0928.pdf"),
        ],
    },
    {
        "doc_no": "BX-2024-1005",
        "applicant": "王强",
        "department": "行政部",
        "reason": "办公室日常采购",
        "submitted_at": "2024-10-05 11:40",
        "status": "approved",
        "lines": [
            ("2024-09-28", "办公用品采购（打印纸、硒鼓）", 38000, 1),
            ("2024-09-29", "快递费", 8000, 1),
        ],
        # 三个文件，但只有两个挂到明细行上
        "attachments": [
            (1, "办公用品发票_0928.pdf"),
            (2, "快递费发票_0929.pdf"),
            (0, "补充说明.pdf"),
        ],
    },
    {
        "doc_no": "BX-2024-1011",
        "applicant": "陈静",
        "department": "市场部-华东区",
        "reason": "华东区客户活动物料",
        "submitted_at": "2024-10-11 16:31",
        "status": "approved",
        "lines": [
            ("2024-10-09", "活动物料制作费", 210000, 1),
            ("2024-10-10", "物料同城配送费", 24000, 1),
        ],
        "attachments": [
            (1, "物料制作发票_1009.pdf"),
            (2, "配送费发票_1010.pdf"),
        ],
    },
    # ---- 干扰单据（让分页成为真问题）--------------------------------------
    {"doc_no": "BX-2024-1019", "applicant": "刘洋", "department": "研发部", "reason": "云服务器续费",
     "submitted_at": "2024-10-19 09:12", "status": "approved",
     "lines": [("2024-10-18", "云服务器 ECS 年度续费", 468000, 1)],
     "attachments": [(1, "阿里云发票_1018.pdf")]},
    {"doc_no": "BX-2024-1018", "applicant": "赵敏", "department": "人力资源部", "reason": "招聘平台年费",
     "submitted_at": "2024-10-18 14:03", "status": "pending",
     "lines": [("2024-10-17", "招聘平台企业版年费", 128000, 1)],
     "attachments": [(1, "招聘平台发票_1017.pdf")]},
    {"doc_no": "BX-2024-1017", "applicant": "孙浩", "department": "研发部", "reason": "技术书籍采购",
     "submitted_at": "2024-10-17 10:55", "status": "approved",
     "lines": [("2024-10-16", "技术书籍 6 本", 43600, 1)],
     "attachments": [(1, "当当网发票_1016.pdf")]},
    {"doc_no": "BX-2024-1016", "applicant": "周婷", "department": "市场部", "reason": "行业展会门票",
     "submitted_at": "2024-10-16 17:20", "status": "approved",
     "lines": [("2024-10-15", "行业展会门票 2 张", 160000, 1)],
     "attachments": [(1, "展会门票_1015.pdf")]},
    {"doc_no": "BX-2024-1015", "applicant": "吴磊", "department": "销售部", "reason": "客户答谢礼品",
     "submitted_at": "2024-10-15 15:08", "status": "rejected",
     "lines": [("2024-10-14", "客户答谢礼品采购", 98000, 1)],
     "attachments": [(1, "礼品发票_1014.pdf")]},
    {"doc_no": "BX-2024-1014", "applicant": "郑爽", "department": "财务部", "reason": "审计服务费",
     "submitted_at": "2024-10-14 09:31", "status": "approved",
     "lines": [("2024-10-13", "外部审计服务费", 350000, 1)],
     "attachments": [(1, "审计服务发票_1013.pdf")]},
    {"doc_no": "BX-2024-1012", "applicant": "刘洋", "department": "研发部", "reason": "开发工具订阅",
     "submitted_at": "2024-10-12 11:12", "status": "pending",
     "lines": [("2024-10-11", "IDE 商业授权（年）", 210000, 1)],
     "attachments": [(1, "JetBrains发票_1011.pdf")]},
    {"doc_no": "BX-2024-1008", "applicant": "孙浩", "department": "研发部", "reason": "测试设备采购",
     "submitted_at": "2024-10-08 16:45", "status": "approved",
     "lines": [
         ("2024-10-07", "安卓测试机 2 台", 259800, 1),
         ("2024-10-07", "测试机保护壳", 6800, 1),
     ],
     "attachments": [(1, "京东发票_1007.pdf"), (2, "配件发票_1007.pdf")]},
    {"doc_no": "BX-2024-1002", "applicant": "周婷", "department": "市场部", "reason": "公众号代运营",
     "submitted_at": "2024-10-02 10:20", "status": "approved",
     "lines": [("2024-10-01", "公众号内容代运营（9 月）", 600000, 1)],
     "attachments": [(1, "代运营服务发票_1001.pdf")]},
    {"doc_no": "BX-2024-0927", "applicant": "赵敏", "department": "人力资源部", "reason": "团建活动",
     "submitted_at": "2024-09-27 18:12", "status": "approved",
     "lines": [("2024-09-26", "部门团建聚餐", 186000, 1)],
     "attachments": [(1, "餐饮发票_0926.pdf")]},
    {"doc_no": "BX-2024-0924", "applicant": "吴磊", "department": "销售部", "reason": "客户来访接待",
     "submitted_at": "2024-09-24 14:38", "status": "approved",
     "lines": [
         ("2024-09-23", "客户来访午餐", 72000, 1),
         ("2024-09-23", "会议室绿植租赁", 15000, 1),
     ],
     "attachments": [(1, "餐饮发票_0923.pdf"), (2, "绿植租赁发票_0923.pdf")]},
    {"doc_no": "BX-2024-0921", "applicant": "郑爽", "department": "财务部", "reason": "银行手续费",
     "submitted_at": "2024-09-21 09:05", "status": "approved",
     "lines": [("2024-09-20", "对公账户年度管理费", 120000, 1)],
     "attachments": [(1, "银行回单_0920.pdf")]},
    {"doc_no": "BX-2024-0918", "applicant": "陈静", "department": "市场部", "reason": "客户资料印刷",
     "submitted_at": "2024-09-18 15:22", "status": "pending",
     "lines": [("2024-09-17", "产品手册印刷 500 份", 128000, 1)],
     "attachments": [(1, "印刷发票_0917.pdf")]},
    {"doc_no": "BX-2024-0915", "applicant": "王强", "department": "行政部", "reason": "饮用水配送",
     "submitted_at": "2024-09-15 08:47", "status": "approved",
     "lines": [("2024-09-14", "桶装水配送（20 桶）", 36000, 1)],
     "attachments": [(1, "桶装水发票_0914.pdf")]},
]
