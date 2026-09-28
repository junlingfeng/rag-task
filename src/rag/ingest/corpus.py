"""合成中英双语知识库。

需求文档没有提供语料，因此这里生成一份可控的知识库：
四类文档（员工手册 / 合规指南 / 技术规范 / 架构文档）、中英混排、
并包含 2 份纯图片扫描件（用于验证 OCR 链路）。

事实条目来自 facts.py，每条都带唯一锚点，便于自动生成 gold chunk 标注。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .facts import FACTS, facts_by_key, validate
from ..textutil import normalize_for_match

RAW_DIR = Path("data/corpus/raw")
MANIFEST_PATH = RAW_DIR / "manifest.json"


@dataclass
class Section:
    heading_zh: str
    heading_en: str
    fact_keys: list[str] = field(default_factory=list)
    filler_zh: str | None = None
    filler_en: str | None = None


@dataclass
class Document:
    doc_id: str
    doc_type: str
    lang: str                      # zh | en | mixed
    title_zh: str
    title_en: str
    sections: list[Section]
    is_scanned: bool = False

    def render_markdown(self) -> str:
        facts = facts_by_key()
        lines: list[str] = []
        if self.lang in ("zh", "mixed"):
            lines.append(f"# {self.title_zh}")
        if self.lang == "en":
            lines.append(f"# {self.title_en}")
        if self.lang == "mixed":
            lines.append(f"## {self.title_en}")
        lines.append("")
        for section in self.sections:
            if self.lang == "en":
                lines.append(f"## {section.heading_en}")
            elif self.lang == "zh":
                lines.append(f"## {section.heading_zh}")
            else:
                lines.append(f"## {section.heading_zh} / {section.heading_en}")
            lines.append("")
            if self.lang in ("zh", "mixed"):
                for key in section.fact_keys:
                    lines.append(facts[key]["zh"])
                    lines.append("")
                if section.filler_zh:
                    lines.append(section.filler_zh)
                    lines.append("")
            if self.lang in ("en", "mixed"):
                for key in section.fact_keys:
                    lines.append(facts[key]["en"])
                    lines.append("")
                if section.filler_en:
                    lines.append(section.filler_en)
                    lines.append("")
        return "\n".join(lines).strip() + "\n"


# 填充内容（filler）：不承载事实，作用是提供干扰项与真实文档的冗长感。
# 没有干扰项，检索任务会退化成"在唯一正确段落里找答案"，三配置差异无法体现。
FILLER: dict[str, list[tuple[str, str, str, str]]] = {
    "handbook": [
        (
            "适用范围",
            "Scope",
            "本章适用于全体正式员工、试用期员工与劳务派遣人员。实习生与外部顾问的相关安排由用人部门与人力资源部另行约定，不适用本章全部条款。",
            "This chapter applies to all regular employees, probationary employees and dispatched staff. Arrangements for interns and external consultants are agreed separately by the hiring department and HR and are not fully covered here.",
        ),
        (
            "职责分工",
            "Roles and Responsibilities",
            "员工负责如实提交申请与证明材料；直属主管负责业务合理性与排班影响审核；部门负责人负责统筹人力安排；人力资源部负责政策解释与最终裁定。",
            "Employees submit accurate applications and supporting documents; direct managers review business rationale and roster impact; department heads coordinate staffing; HR interprets policy and makes final determinations.",
        ),
        (
            "流程与系统",
            "Process and Systems",
            "本章所涉流程均通过人事系统发起，审批链路为直属主管、部门负责人、人力资源部。如遇系统故障，可通过人力资源服务台登记，处理时限为 2 个工作日。",
            "All processes in this chapter are initiated in the HR system, with an approval chain of direct manager, department head and HR. If the system is unavailable, requests may be logged with the HR service desk and are handled within 2 working days.",
        ),
        (
            "记录与归档",
            "Records and Archiving",
            "所有审批记录由人事系统自动归档，保存期限与员工劳动关系存续期一致。员工可通过自助门户查询本人历史记录，他人无权代为调阅。",
            "All approval records are archived automatically by the HR system for the duration of the employment relationship. Employees may view their own history through the self-service portal; third parties have no access.",
        ),
        (
            "违规与申诉",
            "Violations and Appeals",
            "对本章条款的违反将视情节给予提醒、书面警告直至解除劳动合同的处理。员工对处理结果有异议的，可在收到通知后向人力资源部提出申诉。",
            "Violations may result in a reminder, written warning or termination depending on severity. Employees who disagree with an outcome may appeal to HR after receiving notice.",
        ),
        (
            "术语说明",
            "Definitions",
            "本章所称'工作日'指法定工作日，不含法定节假日与周末；所称'直属主管'指员工组织架构中的直接汇报对象，不含项目虚线的汇报关系。",
            "In this chapter, 'working day' means a statutory working day excluding public holidays and weekends, and 'direct manager' means the direct reporting line, excluding project-based dotted-line relationships.",
        ),
    ],
    "compliance": [
        (
            "适用范围",
            "Scope",
            "本指南适用于全体董事、管理人员与员工，以及代表公司行事的第三方代理、顾问与供应商。第三方违反本指南可能导致合同解除。",
            "This guide applies to all directors, managers and employees, as well as third-party agents, consultants and suppliers acting on behalf of the company. Violations by third parties may lead to contract termination.",
        ),
        (
            "合规职责",
            "Compliance Responsibilities",
            "业务部门负责人对本部门合规结果负第一责任；合规部门负责政策制定、培训与调查；内部审计负责独立评估控制有效性。",
            "Business leaders hold first-line responsibility for compliance outcomes in their units; Compliance sets policy, delivers training and conducts investigations; Internal Audit independently assesses control effectiveness.",
        ),
        (
            "培训与沟通",
            "Training and Communication",
            "新员工须在入职后完成合规基础课程；在岗员工每年参加一次合规复训。合规部门通过邮件与内网公告发布政策更新。",
            "New hires complete foundational compliance training after onboarding; existing staff attend annual refresher sessions. Policy updates are communicated by email and the intranet.",
        ),
        (
            "记录与举证",
            "Records and Evidence",
            "合规相关审批、申报与调查记录由合规系统留存，业务部门不得自行删除或修改。调查过程遵循保密原则。",
            "Compliance approvals, declarations and investigation records are kept in the compliance system; business units must not delete or alter them. Investigations follow confidentiality principles.",
        ),
        (
            "违规后果",
            "Consequences",
            "违反合规政策的员工可能面临纪律处分、解除劳动合同、追偿损失以及移交司法机关处理。管理层未尽监督职责的，一并追究管理责任。",
            "Employees violating compliance policy may face disciplinary action, termination, recovery of losses or referral to authorities. Managers who fail to supervise may be held accountable as well.",
        ),
        (
            "政策复审机制",
            "Policy Review",
            "合规部门每年组织一次政策复审，并根据法规变化发布更新版本。员工有义务阅读最新版本并在系统中确认知悉。",
            "The Compliance function reviews these policies annually and publishes updates when regulations change. Employees are required to read the latest version and acknowledge it in the system.",
        ),
    ],
    "tech_spec": [
        (
            "适用范围",
            "Scope",
            "本规范适用于所有面向内部与外部开放的平台接口，包括同步接口、异步任务接口与事件通知。遗留系统的改造范围由架构评审委员会单独确定。",
            "This specification applies to all platform APIs, internal and external, including synchronous endpoints, asynchronous jobs and event notifications. Scope for legacy system remediation is determined separately by the Architecture Review Board.",
        ),
        (
            "设计与评审",
            "Design and Review",
            "接口设计须先提交接口描述文件并经过同行评审；涉及跨域调用的，须补充容量评估与故障影响分析。",
            "Interface designs must be submitted as a specification and peer reviewed. Cross-domain calls additionally require capacity assessment and failure impact analysis.",
        ),
        (
            "变更管理",
            "Change Management",
            "接口变更须通过架构评审委员会评审，并提前公告。破坏性变更必须提供新版本并保留过渡期，不得直接修改既有语义。",
            "Interface changes require Architecture Review Board approval and advance notice. Breaking changes must ship as a new version with a transition period and must not silently alter existing semantics.",
        ),
        (
            "测试与验收",
            "Testing and Acceptance",
            "接口上线前须完成契约测试、异常场景测试与压力测试，并提供测试报告。未通过验收的接口不得开放给调用方。",
            "Before release, APIs must pass contract tests, exception-path tests and load tests with a published report. APIs that fail acceptance must not be exposed to consumers.",
        ),
        (
            "监控与告警",
            "Monitoring and Alerting",
            "所有接口须接入统一监控，覆盖成功率、延迟分位数、错误码分布与限流触发次数，并配置分级告警阈值。",
            "All APIs must be onboarded to unified monitoring covering success rate, latency percentiles, error code distribution and throttling events, with tiered alert thresholds.",
        ),
        (
            "文档要求",
            "Documentation",
            "接口文档须包含用途、鉴权方式、请求与响应示例、错误码清单、限流策略与变更历史，并随接口变更同步更新。",
            "API documentation must include purpose, authentication, request and response examples, error code catalogue, rate limiting policy and change history, updated alongside the interface.",
        ),
    ],
    "architecture": [
        (
            "设计目标",
            "Design Goals",
            "平台架构以高可用、可扩展与可观测为核心目标，优先保证核心交易链路的数据一致性与故障隔离能力。",
            "The platform architecture targets high availability, scalability and observability, prioritising data consistency and fault isolation on core transactional paths.",
        ),
        (
            "分层与边界",
            "Layering and Boundaries",
            "系统分为接入层、应用层、领域服务层与数据层。跨层调用须经过明确定义的接口，禁止数据层被应用层直接访问。",
            "The system is layered into access, application, domain service and data tiers. Cross-tier calls go through defined interfaces; direct data-tier access from the application tier is prohibited.",
        ),
        (
            "容错与降级",
            "Fault Tolerance and Degradation",
            "依赖外部服务时须设置超时、重试与熔断策略；降级方案需明确业务影响范围，并在演练中验证有效性。",
            "Calls to external services require timeouts, retries and circuit breakers. Degradation plans must state business impact and be validated in drills.",
        ),
        (
            "容量与扩展",
            "Capacity and Scaling",
            "容量评估按峰值流量的两倍设计，无状态服务支持水平扩展，有状态组件通过分片或读写分离提升吞吐。",
            "Capacity is provisioned at twice peak traffic. Stateless services scale horizontally; stateful components scale through sharding or read-write splitting.",
        ),
        (
            "安全设计",
            "Security Design",
            "架构遵循最小权限与零信任原则，服务间调用须完成身份认证与授权，敏感配置通过密钥管理服务下发。",
            "The architecture follows least privilege and zero trust. Service-to-service calls require authentication and authorisation, and secrets are delivered through a key management service.",
        ),
        (
            "架构决策记录",
            "ADR",
            "架构决策以 ADR（架构决策记录）形式沉淀，重大变更需经架构评审委员会批准。本文档描述目标架构，实际部署以配置仓库为准。",
            "Architecture decisions are recorded as ADRs, and material changes require Architecture Review Board approval. This document describes the target architecture; the configuration repository is authoritative.",
        ),
    ],
}

# 补充文档使用的地域与版本，用来生成与主文档相似但内容不同的干扰文档。
# 真实内部知识库中大量存在这类"某地补充规定"，它们正是检索的主要干扰来源。
REGIONS: tuple[tuple[str, str], ...] = (
    ("上海研发中心", "Shanghai R&D Center"),
    ("北京分部", "Beijing Branch"),
    ("深圳交付中心", "Shenzhen Delivery Center"),
    ("新加坡办公室", "Singapore Office"),
    ("香港分公司", "Hong Kong Branch"),
    ("东京代表处", "Tokyo Representative Office"),
    ("伦敦办公室", "London Office"),
    ("纽约办公室", "New York Office"),
)

_SUPPLEMENT_PREFIX: dict[str, tuple[str, str, str]] = {
    # doc_type: (doc_id 段, 中文标题前缀, 英文标题前缀)
    "handbook": ("HB", "员工手册补充规定", "Handbook Supplement"),
    "compliance": ("CP", "合规指南补充规定", "Compliance Supplement"),
    "tech_spec": ("TS", "技术规范补充规定", "Technical Specification Supplement"),
    "architecture": ("AR", "架构文档补充规定", "Architecture Supplement"),
}


def build_supplemental_documents() -> list[Document]:
    """生成地域补充文档：不含事实，仅作为检索干扰项。"""
    documents: list[Document] = []
    for doc_type, (code, title_zh_prefix, title_en_prefix) in _SUPPLEMENT_PREFIX.items():
        pool = FILLER[doc_type]
        for index, (region_zh, region_en) in enumerate(REGIONS):
            # 单语交替：保证语料在中文、英文、混排三种形态上都有覆盖
            doc_lang = "zh" if index % 2 == 0 else "en"
            sections: list[Section] = []
            for offset in range(3):
                heading_zh, heading_en, zh, en = pool[(index + offset) % len(pool)]
                sections.append(
                    Section(
                        heading_zh,
                        heading_en,
                        [],
                        filler_zh=f"{region_zh}实施细则：{zh}本补充规定自 {2020 + index} 版起生效。",
                        filler_en=f"{region_en} implementation: {en} This supplement is effective from version {2020 + index}.",
                    )
                )
            documents.append(
                Document(
                    doc_id=f"DOC-{code}-S{index + 1:02d}",
                    doc_type=doc_type,
                    lang=doc_lang,
                    title_zh=f"{title_zh_prefix} · {region_zh}",
                    title_en=f"{title_en_prefix} - {region_en}",
                    sections=sections,
                )
            )
    return documents


def build_documents() -> list[Document]:
    def filler_sections(doc_type: str, offset: int, count: int = 4) -> list[Section]:
        """按偏移量轮换取用填充章节，避免所有同类文档完全雷同。"""
        pool = FILLER[doc_type]
        picked = [pool[(offset + i) % len(pool)] for i in range(count)]
        return [
            Section(heading_zh, heading_en, [], filler_zh=zh, filler_en=en)
            for heading_zh, heading_en, zh, en in picked
        ]

    documents = [
        Document(
            doc_id="DOC-HB-01",
            doc_type="handbook",
            lang="zh",
            title_zh="员工手册 · 休假与考勤",
            title_en="Employee Handbook - Leave and Attendance",
            sections=[
                Section("年假", "Annual Leave", ["annual_leave_days"]),
                Section("病假", "Sick Leave", ["sick_leave_deadline"]),
                Section("加班与调休", "Overtime", ["overtime_compensation"]),
                Section("远程办公", "Remote Work", ["remote_work_days"]),
            ]
            + filler_sections("handbook", 0),
        ),
        Document(
            doc_id="DOC-HB-02",
            doc_type="handbook",
            lang="en",
            title_zh="员工手册 · 雇佣与薪酬",
            title_en="Employee Handbook - Employment and Rewards",
            sections=[
                Section("试用期", "Probation", ["probation_period"]),
                Section("差旅报销", "Travel Reimbursement", ["travel_reimbursement_window"]),
                Section("离职流程", "Resignation", ["resignation_notice"]),
                Section("培训与认证", "Training and Certification", ["training_budget"]),
            ]
            + filler_sections("handbook", 2),
        ),
        Document(
            doc_id="DOC-CP-01",
            doc_type="compliance",
            lang="zh",
            title_zh="合规指南 · 商业行为准则",
            title_en="Compliance Guide - Code of Business Conduct",
            sections=[
                Section("礼品与招待", "Gifts and Hospitality", ["gift_value_limit"]),
                Section("利益冲突申报", "Conflict of Interest", ["conflict_of_interest"]),
                Section("第三方尽调", "Third-Party Due Diligence", ["third_party_due_diligence"]),
                Section("反腐培训", "Anti-Corruption Training", ["anti_corruption_training"]),
            ]
            + filler_sections("compliance", 0),
        ),
        Document(
            doc_id="DOC-CP-02",
            doc_type="compliance",
            lang="mixed",
            title_zh="合规指南 · 信息与数据保护",
            title_en="Compliance Guide - Information and Data Protection",
            sections=[
                Section("数据分级", "Data Classification", ["data_classification"]),
                Section("内幕信息与交易窗口", "Inside Information", ["trading_blackout"]),
                Section("审计记录保存", "Audit Record Retention", ["audit_record_retention"]),
                Section("举报渠道", "Whistleblowing Channel", ["reporting_channel"]),
            ]
            + filler_sections("compliance", 3),
            is_scanned=True,
        ),
        Document(
            doc_id="DOC-TS-01",
            doc_type="tech_spec",
            lang="en",
            title_zh="技术规范 · 开放平台接入",
            title_en="Technical Specification - Open Platform Access",
            sections=[
                Section("速率限制", "Rate Limiting", ["rate_limit"]),
                Section("认证与令牌", "Authentication", ["access_token_ttl"]),
                Section("分页约定", "Pagination", ["pagination_defaults"]),
                Section("超时设置", "Timeouts", ["gateway_timeout"]),
            ]
            + filler_sections("tech_spec", 0),
        ),
        Document(
            doc_id="DOC-TS-02",
            doc_type="tech_spec",
            lang="zh",
            title_zh="技术规范 · 安全与可观测",
            title_en="Technical Specification - Security and Observability",
            sections=[
                Section("加密标准", "Encryption", ["encryption_standard"]),
                Section("日志保留", "Log Retention", ["log_retention"]),
                Section("版本管理", "Versioning", ["api_version_header"]),
                Section("错误码规范", "Error Codes", ["error_code_format"]),
            ]
            + filler_sections("tech_spec", 3),
        ),
        Document(
            doc_id="DOC-AR-01",
            doc_type="architecture",
            lang="mixed",
            title_zh="架构文档 · 核心平台",
            title_en="Architecture Document - Core Platform",
            sections=[
                Section("数据存储", "Data Storage", ["primary_database"]),
                Section("消息队列", "Messaging", ["message_queue"]),
                Section("缓存层", "Cache Layer", ["cache_cluster"]),
                Section("接入网关", "API Gateway", ["api_gateway"]),
            ]
            + filler_sections("architecture", 0),
        ),
        Document(
            doc_id="DOC-AR-02",
            doc_type="architecture",
            lang="en",
            title_zh="架构文档 · 部署与运维",
            title_en="Architecture Document - Deployment and Operations",
            sections=[
                Section("部署拓扑", "Deployment Topology", ["deployment_topology"]),
                Section("可观测体系", "Observability", ["observability_stack"]),
                Section("备份策略", "Backup Policy", ["backup_policy"]),
                Section("可用性目标", "Availability Target", ["availability_sla"]),
            ]
            + filler_sections("architecture", 3),
            is_scanned=True,
        ),
    ]
    documents.extend(build_supplemental_documents())
    return documents


def build_corpus(raw_dir: Path = RAW_DIR, render_scanned: bool = True) -> dict:
    """生成语料文件与清单，返回 manifest。"""
    validate()
    # 填充文本不得包含任何锚点，否则锚点会命中无关 chunk。
    filler_text = normalize_for_match(
        " ".join(f"{zh} {en}" for pool in FILLER.values() for _, _, zh, en in pool)
    )
    for fact in FACTS:
        assert normalize_for_match(fact["anchor_zh"]) not in filler_text, f"锚点出现在填充文本中: {fact['key']}"
        assert normalize_for_match(fact["anchor_en"]) not in filler_text, f"锚点出现在填充文本中: {fact['key']}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    documents = build_documents()
    manifest: dict = {"corpus_version": "kb_v1", "documents": [], "facts": []}

    for doc in documents:
        if doc.is_scanned and render_scanned:
            from .scanned import render_scanned_pdf

            pdf_path = raw_dir / f"{doc.doc_id}.pdf"
            text_path = raw_dir / f"{doc.doc_id}.ocr.txt"
            pages = render_scanned_pdf(doc, pdf_path)
            # 旁路文本：仅在 OCR 依赖不可用时作为降级来源，正常路径不使用。
            text_path.write_text(doc.render_markdown(), encoding="utf-8")
            path = pdf_path
            extra = {"pages": pages, "ocr_sidecar": text_path.name}
        else:
            path = raw_dir / f"{doc.doc_id}.md"
            path.write_text(doc.render_markdown(), encoding="utf-8")
            extra = {"pages": None, "ocr_sidecar": None}

        manifest["documents"].append(
            {
                "doc_id": doc.doc_id,
                "title_zh": doc.title_zh,
                "title_en": doc.title_en,
                "doc_type": doc.doc_type,
                "lang": doc.lang,
                "is_scanned": doc.is_scanned,
                "path": str(path),
                "facts": [k for s in doc.sections for k in s.fact_keys],
                **extra,
            }
        )

    for fact in FACTS:
        manifest["facts"].append(
            {
                "key": fact["key"],
                "doc_type": fact["doc_type"],
                "anchor_zh": fact["anchor_zh"],
                "anchor_en": fact["anchor_en"],
                "q_zh": fact["q_zh"],
                "q_en": fact["q_en"],
                "a_zh": fact["a_zh"],
                "a_en": fact["a_en"],
            }
        )

    manifest["stats"] = {
        "documents": len(manifest["documents"]),
        "scanned_documents": sum(1 for d in manifest["documents"] if d["is_scanned"]),
        "facts": len(manifest["facts"]),
        "languages": sorted({d["lang"] for d in manifest["documents"]}),
        "doc_types": sorted({d["doc_type"] for d in manifest["documents"]}),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = build_corpus()
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))
