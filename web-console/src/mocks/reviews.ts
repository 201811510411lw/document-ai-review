import type { ReviewDetail } from "../api/reviews";

export const mockReviews: ReviewDetail[] = [
  {
    taskId: "blr-20260615-0001",
    businessName: "成都示例商贸有限公司",
    creditCode: "91510100MA0000000X",
    reviewStatus: "REVIEWED",
    reviewStatusLabel: "已审核",
    riskLevel: "NONE",
    riskLevelLabel: "无风险",
    needsManualReview: false,
    reviewedAt: "2026-06-15T09:18:00+08:00",
    sourceRecordId: "SRM-CERT-884201",
    attachmentId: "ATT-BL-240601",
    sourceUrl: "https://files.example.test/business-license-0001.pdf",
    summary: "主体名称、统一社会信用代码和有效期均通过规则校验。",
    extractedFields: {
      subjectName: "成都示例商贸有限公司",
      creditCode: "91510100MA0000000X",
      legalPerson: "张三",
      establishedDate: "2020-01-02",
      validFrom: "2020-01-02",
      validTo: "长期",
      businessAddress: "成都市高新区天府大道 1 号",
      confidence: 0.97
    },
    normalizedFields: {
      subjectName: "成都示例商贸有限公司",
      creditCode: "91510100MA0000000X",
      legalPerson: "张三",
      establishedDate: "2020-01-02",
      validFrom: "2020-01-02",
      validTo: "长期",
      businessAddress: "成都市高新区天府大道1号",
      confidence: 0.97
    },
    ruleResults: [
      {
        ruleCode: "BUSINESS_LICENSE_TYPE_MATCH",
        ruleName: "证照类型匹配",
        state: "passed",
        riskLevelOnFailure: "HIGH",
        message: "已确认文件为营业执照"
      },
      {
        ruleCode: "BUSINESS_LICENSE_SUBJECT_NAME_MATCH",
        ruleName: "主体名称匹配",
        state: "passed",
        riskLevelOnFailure: "MEDIUM",
        message: "证照主体名称与来源系统供应商名称一致"
      },
      {
        ruleCode: "BUSINESS_LICENSE_CREDIT_CODE_MATCH",
        ruleName: "统一社会信用代码匹配",
        state: "passed",
        riskLevelOnFailure: "HIGH",
        message: "统一社会信用代码一致且格式有效"
      }
    ],
    manualReviewReasons: [],
    manualReview: {
      status: "NOT_REQUIRED",
      reasons: []
    },
    auditEvents: [],
    payload: {
      status: "REVIEWED",
      risk_level: "NONE",
      needs_manual_review: false,
      skill_result: {
        extracted_fields: {
          subject_name: "成都示例商贸有限公司",
          credit_code: "91510100MA0000000X"
        }
      }
    }
  },
  {
    taskId: "blr-20260615-0002",
    businessName: "上海云岚供应链管理有限公司",
    creditCode: "91310115MA1K00002Q",
    reviewStatus: "PENDING_MANUAL_REVIEW",
    reviewStatusLabel: "待人工复核",
    riskLevel: "HIGH",
    riskLevelLabel: "高风险",
    needsManualReview: true,
    reviewedAt: "2026-06-15T10:36:00+08:00",
    sourceRecordId: "SRM-CERT-884245",
    attachmentId: "ATT-BL-240645",
    sourceUrl: "https://files.example.test/business-license-0002.png",
    summary: "统一社会信用代码与来源系统不一致，需要人工核对原件。",
    extractedFields: {
      subjectName: "上海云岚供应链管理有限公司",
      creditCode: "91310115MA1K00002R",
      legalPerson: "李四",
      establishedDate: "2019-07-11",
      validFrom: "2019-07-11",
      validTo: "2029-07-10",
      businessAddress: "上海市浦东新区张江路 88 号",
      confidence: 0.91
    },
    normalizedFields: {
      subjectName: "上海云岚供应链管理有限公司",
      creditCode: "91310115MA1K00002R",
      legalPerson: "李四",
      establishedDate: "2019-07-11",
      validFrom: "2019-07-11",
      validTo: "2029-07-10",
      businessAddress: "上海市浦东新区张江路88号",
      confidence: 0.91
    },
    ruleResults: [
      {
        ruleCode: "BUSINESS_LICENSE_SUBJECT_NAME_MATCH",
        ruleName: "主体名称匹配",
        state: "passed",
        riskLevelOnFailure: "MEDIUM",
        message: "主体名称一致"
      },
      {
        ruleCode: "BUSINESS_LICENSE_CREDIT_CODE_MATCH",
        ruleName: "统一社会信用代码匹配",
        state: "failed",
        riskLevelOnFailure: "HIGH",
        message: "来源系统信用代码为 91310115MA1K00002Q，证照识别为 91310115MA1K00002R",
        evidence: "统一社会信用代码 91310115MA1K00002R"
      },
      {
        ruleCode: "BUSINESS_LICENSE_VALIDITY_PERIOD",
        ruleName: "营业期限有效",
        state: "passed",
        riskLevelOnFailure: "HIGH",
        message: "营业期限未过期"
      }
    ],
    manualReviewReasons: ["统一社会信用代码不一致"],
    manualReview: {
      status: "PENDING",
      reasons: ["统一社会信用代码不一致"]
    },
    auditEvents: [],
    payload: {
      status: "PENDING_MANUAL_REVIEW",
      risk_level: "HIGH",
      needs_manual_review: true,
      manual_review: {
        status: "PENDING",
        reasons: ["统一社会信用代码不一致"]
      }
    }
  },
  {
    taskId: "blr-20260615-0003",
    businessName: "苏州复核完成商贸有限公司",
    creditCode: "91320500MA1K00003A",
    reviewStatus: "MANUAL_REVIEWED",
    reviewStatusLabel: "人工已复核",
    riskLevel: "HIGH",
    riskLevelLabel: "高风险",
    needsManualReview: false,
    reviewedAt: "2026-06-15T11:20:00+08:00",
    sourceRecordId: "SRM-CERT-884266",
    attachmentId: "ATT-BL-240666",
    sourceUrl: "https://files.example.test/business-license-0003.png",
    summary: "人工复核确认原始营业执照信息。",
    extractedFields: {
      subjectName: "苏州复核完成商贸有限公司",
      creditCode: "91320500MA1K00003A",
      legalPerson: "陈七",
      establishedDate: "2022-05-16",
      validFrom: "2022-05-16",
      validTo: "2032-05-15",
      businessAddress: "苏州市工业园区示例路 18 号",
      confidence: 0.9
    },
    normalizedFields: {
      subjectName: "苏州复核完成商贸有限公司",
      creditCode: "91320500MA1K00003A",
      legalPerson: "陈七",
      establishedDate: "2022-05-16",
      validFrom: "2022-05-16",
      validTo: "2032-05-15",
      businessAddress: "苏州市工业园区示例路18号",
      confidence: 0.9
    },
    ruleResults: [],
    manualReviewReasons: ["统一社会信用代码不一致"],
    manualReview: {
      status: "COMPLETED",
      decision: "approved",
      comment: "已核对原件，确认通过。",
      reviewerId: "wecom-reviewer-001",
      reviewerUsername: "reviewer",
      reviewedAt: "2026-06-15T11:20:00+08:00",
      reasons: ["统一社会信用代码不一致"]
    },
    auditEvents: [
      {
        eventType: "BUSINESS_LICENSE_MANUAL_REVIEW",
        message: "人工复核确认通过",
        occurredAt: "2026-06-15T11:20:00+08:00",
        actorId: "wecom-reviewer-001",
        actorUsername: "reviewer",
        details: {
          decision: "approved",
          comment: "已核对原件，确认通过。",
          reviewer_id: "wecom-reviewer-001",
          reviewer_username: "reviewer"
        }
      }
    ],
    payload: {
      status: "MANUAL_REVIEWED",
      risk_level: "HIGH",
      needs_manual_review: false,
      manual_review: {
        status: "COMPLETED",
        decision: "approved",
        reasons: ["统一社会信用代码不一致"]
      }
    }
  },
  {
    taskId: "blr-20260614-0018",
    businessName: "杭州简禾食品科技有限公司",
    creditCode: "91330108MA2B00003U",
    reviewStatus: "PENDING_MANUAL_REVIEW",
    reviewStatusLabel: "待人工复核",
    riskLevel: "MEDIUM",
    riskLevelLabel: "中风险",
    needsManualReview: true,
    reviewedAt: "2026-06-14T16:52:00+08:00",
    sourceRecordId: "SRM-CERT-883901",
    attachmentId: "ATT-BL-240512",
    sourceUrl: "https://files.example.test/business-license-0018.pdf",
    summary: "营业期限字段有值但无法解析，需人工确认是否长期有效。",
    extractedFields: {
      subjectName: "杭州简禾食品科技有限公司",
      creditCode: "91330108MA2B00003U",
      legalPerson: "王五",
      establishedDate: "2021-03-05",
      validFrom: "2021-03-05",
      validTo: "见章程",
      businessAddress: "杭州市滨江区江南大道 1688 号",
      confidence: 0.84
    },
    normalizedFields: {
      subjectName: "杭州简禾食品科技有限公司",
      creditCode: "91330108MA2B00003U",
      legalPerson: "王五",
      establishedDate: "2021-03-05",
      validFrom: "2021-03-05",
      validTo: "见章程",
      businessAddress: "杭州市滨江区江南大道1688号",
      confidence: 0.84
    },
    ruleResults: [
      {
        ruleCode: "BUSINESS_LICENSE_VALIDITY_PERIOD",
        ruleName: "营业期限有效",
        state: "manual_review",
        riskLevelOnFailure: "MEDIUM",
        message: "有效期字段无法自动判断"
      }
    ],
    manualReviewReasons: ["有效期无法判断"],
    manualReview: {
      status: "PENDING",
      reasons: ["有效期无法判断"]
    },
    auditEvents: [],
    payload: {
      status: "PENDING_MANUAL_REVIEW",
      risk_level: "MEDIUM",
      needs_manual_review: true,
      manual_review: {
        status: "PENDING",
        reasons: ["有效期无法判断"]
      }
    }
  },
  {
    taskId: "blr-20260613-0024",
    businessName: "深圳岭南电子商务有限公司",
    creditCode: "91440300MA5D00004M",
    reviewStatus: "REVIEWED",
    reviewStatusLabel: "已审核",
    riskLevel: "NONE",
    riskLevelLabel: "无风险",
    needsManualReview: false,
    reviewedAt: "2026-06-13T11:05:00+08:00",
    sourceRecordId: "SRM-CERT-883508",
    attachmentId: "ATT-BL-240433",
    sourceUrl: "https://files.example.test/business-license-0024.jpg",
    summary: "主体名称存在标点差异，核心字号与组织形式一致，自动通过并记录说明。",
    extractedFields: {
      subjectName: "深圳岭南电子商务有限公司",
      creditCode: "91440300MA5D00004M",
      legalPerson: "赵六",
      establishedDate: "2018-12-20",
      validFrom: "2018-12-20",
      validTo: "长期",
      businessAddress: "深圳市南山区科技园科苑路 12 号",
      confidence: 0.89
    },
    normalizedFields: {
      subjectName: "深圳岭南电子商务有限公司",
      creditCode: "91440300MA5D00004M",
      legalPerson: "赵六",
      establishedDate: "2018-12-20",
      validFrom: "2018-12-20",
      validTo: "长期",
      businessAddress: "深圳市南山区科技园科苑路12号",
      confidence: 0.89
    },
    ruleResults: [
      {
        ruleCode: "BUSINESS_LICENSE_SUBJECT_NAME_MATCH",
        ruleName: "主体名称匹配",
        state: "passed",
        riskLevelOnFailure: "MEDIUM",
        message: "仅存在标点差异，视为一致"
      }
    ],
    manualReviewReasons: [],
    manualReview: {
      status: "NOT_REQUIRED",
      reasons: []
    },
    auditEvents: [],
    payload: {
      status: "REVIEWED",
      risk_level: "NONE",
      needs_manual_review: false
    }
  },
  {
    taskId: "qc-task-1",
    businessName: "成都示例食品有限公司",
    creditCode: "91510100MA00000000",
    reviewStatus: "PENDING_MANUAL_REVIEW",
    reviewStatusLabel: "待人工复核",
    riskLevel: "MEDIUM",
    riskLevelLabel: "中风险",
    needsManualReview: true,
    reviewedAt: "2026-06-12T10:00:00+08:00",
    sourceRecordId: "SRM-FOOD-001",
    attachmentId: "ATT-FOOD-001",
    sourceUrl: "https://files.example.test/food-license.pdf",
    summary: "经营范围需要人工确认。",
    extractedFields: {
      subjectName: "成都示例食品有限公司",
      creditCode: "91510100MA00000000",
      legalPerson: "李四",
      establishedDate: "",
      validFrom: "2024-01-01",
      validTo: "2029-01-01",
      businessAddress: "成都市示例区示例路 100 号",
      confidence: 0.88
    },
    normalizedFields: {
      subjectName: "成都示例食品有限公司",
      creditCode: "91510100MA00000000",
      legalPerson: "李四",
      establishedDate: "",
      validFrom: "2024-01-01",
      validTo: "2029-01-01",
      businessAddress: "成都市示例区示例路100号",
      confidence: 0.88
    },
    ruleResults: [],
    manualReviewReasons: ["经营范围需要人工确认"],
    manualReview: {
      status: "PENDING",
      reasons: ["经营范围需要人工确认"]
    },
    auditEvents: [],
    payload: {
      task_id: "qc-task-1",
      document_type: "food_license",
      status: "PENDING_MANUAL_REVIEW"
    }
  }
];
