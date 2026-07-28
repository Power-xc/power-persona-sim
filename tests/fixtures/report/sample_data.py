"""리포트 테스트용 fixture 샘플 데이터."""

from datetime import UTC, datetime

from power_persona_sim.contracts import (
    CellAssignment,
    CellSpec,
    Goal,
    Knowledge,
    Lever,
    PersonaRecord,
    Question,
    QuestionType,
    ResponseRecord,
    SampleManifest,
    Survey,
    ValidationCheck,
    ValidationReport,
)


def create_sample_personas() -> list[PersonaRecord]:
    """데모용 페르소나 3명."""
    return [
        PersonaRecord(
            uuid="persona-001",
            sex="남자",
            age=45,
            marital_status="배우자있음",
            family_type="배우자와 거주",
            housing_type="아파트",
            education_level="4년제 대학교",
            occupation="회계 사무원",
            district="서울-강남구",
            province="서울",
            persona="박준영 씨는 서울에서 IT 회사 팀장으로 일하는 45세 남성으로, 일과 가정의 균형을 중시합니다.",
            culinary_persona="주말에 아내와 함께 고급 레스토랑을 찾아다니며, 갈비찜 같은 격식 있는 음식을 선호합니다.",
            family_persona="배우자와 함께 생활하며 주말에는 가족 행사를 중시합니다.",
            hobbies_and_interests="와인 감상, 미식 여행, 골프",
        ),
        PersonaRecord(
            uuid="persona-002",
            sex="여자",
            age=38,
            marital_status="배우자있음",
            family_type="배우자와 자녀와 거주",
            housing_type="아파트",
            education_level="4년제 대학교",
            occupation="마케팅 담당자",
            district="서울-서초구",
            province="서울",
            persona="이수진 씨는 36세 여성으로 두 자녀를 둔 바쁜 직장맘입니다.",
            culinary_persona="평일에는 간편식을 자주 이용하지만, 명절에는 정성스러운 갈비찜을 준비하곤 합니다.",
            family_persona="자녀의 성장을 최우선으로 생각하며, 가족식사를 소중히 여깁니다.",
            hobbies_and_interests="아이 교육, 요리, 독서",
        ),
        PersonaRecord(
            uuid="persona-003",
            sex="남자",
            age=62,
            marital_status="배우자있음",
            family_type="배우자와 거주",
            housing_type="아파트",
            education_level="고등학교",
            occupation="은퇴",
            district="광주-동구",
            province="광주",
            persona="이강호 씨는 62세 남성으로 최근 은퇴한 후 여유로운 생활을 즐기고 있습니다.",
            culinary_persona="주중에는 아내와 함께 간단한 식사를 하지만, 손주들이 방문할 때는 갈비찜을 준비합니다.",
            family_persona="손주들과 시간을 보내는 것이 큰 즐거움입니다.",
            hobbies_and_interests="낚시, 텃밭 가꾸기, 손주 돌보기",
        ),
    ]


def create_sample_survey() -> Survey:
    """데모용 미니 설문."""
    levers = [
        Lever(id="L1", name="인지·도달"),
        Lever(id="L2", name="제품 사양"),
        Lever(id="L3", name="가격·프로모션"),
        Lever(id="L4", name="유통 채널"),
        Lever(id="L5", name="메시지·패키지"),
    ]

    goal = Goal(
        business_goal="청와연 갈비찜의 자사 브랜드 구매자 전환",
        decision="전환 예산을 어디에 투입할 것인가",
        levers=levers,
        success_criteria="5개 레버에 우선순위와 근거가 붙고, 레버별 검증 가능한 전환 가설 1개 이상 도출",
        one_sentence="갈비찜을 사는 사람이 청와연을 안 사는 이유는 [격식 이미지]이며, [상시 라인업]을 만들면 [일상 수요층]이 전환된다",
    )

    knowledge = [
        Knowledge(
            id="K1",
            statement="카테고리를 언제·왜 사는가 (JTBD·상황 트리거)",
            lever_ids=["L1", "L5"],
            judgement_rule="트리거가 특정 시즌에 80% 집중 → 시즌 집중 투자",
        ),
        Knowledge(
            id="K2",
            statement="현재 무엇을 사는가 = 실제 경쟁자 집합",
            lever_ids=["L2"],
            judgement_rule="경쟁이 타 브랜드면 브랜드전, 직접조리면 카테고리전",
        ),
        Knowledge(
            id="K3",
            statement="자사 인지 여부와 인지 경로",
            lever_ids=["L1"],
            judgement_rule="미인지 ≥ 50% → 문제는 도달",
        ),
        Knowledge(
            id="K4",
            statement="인지자가 고려군에 안 넣는 이유",
            lever_ids=["L5"],
            judgement_rule="가격 이미지 지배 → 가치 근거 강화",
        ),
    ]

    questions = [
        Question(
            id="S1",
            section="S",
            text="최근 12개월 내 갈비찜을 구매한 적이 있나요?",
            qtype=QuestionType.SINGLE,
            knowledge_ids=["K1"],
            options=["예", "아니요"],
        ),
        Question(
            id="K1_1",
            section="A",
            text="가장 최근에 갈비찜을 구매하게 된 상황은?",
            qtype=QuestionType.SINGLE,
            knowledge_ids=["K1"],
            options=["명절", "기념일", "주말 가족식사", "손님 접대", "평일 반찬", "기타"],
        ),
        Question(
            id="K2_1",
            section="B",
            text="그때 함께 고려한 대안은? (복수 선택)",
            qtype=QuestionType.MULTI,
            knowledge_ids=["K2"],
            options=["타 브랜드 갈비찜", "직접 조리", "외식", "배달 음식", "다른 메뉴"],
        ),
        Question(
            id="K3_1",
            section="B",
            text="청와연 브랜드를 알고 있나요?",
            qtype=QuestionType.SINGLE,
            knowledge_ids=["K3"],
            options=["처음 들음", "이름은 들었지만 자세히 모름", "알고 있음"],
        ),
        Question(
            id="K4_1",
            section="C",
            text="청와연 갈비찜에 대한 느낌은? (1=매우 부정, 5=매우 긍정)",
            qtype=QuestionType.SCALE,
            knowledge_ids=["K4"],
            scale_points=5,
        ),
    ]

    return Survey(
        id="cheongwayeon-v1",
        goal=goal,
        knowledge=knowledge,
        questions=questions,
    )


def create_sample_responses() -> list[ResponseRecord]:
    """데모용 응답 3명 × 5문항."""
    responses = []
    personas = create_sample_personas()
    questions = create_sample_survey().questions

    for rep in range(len(personas)):  # 3명
        for q_idx, q in enumerate(questions):
            if q.qtype == QuestionType.SINGLE:
                parsed = q.options[0]
            elif q.qtype == QuestionType.MULTI:
                parsed = [q.options[0]]
            elif q.qtype == QuestionType.SCALE:
                parsed = 4 - (rep % 2)  # 3, 4, 3
            else:
                parsed = None

            responses.append(
                ResponseRecord(
                    run_id="demo-run-001",
                    persona_uuid=personas[rep].uuid,
                    question_id=q.id,
                    repetition=1,
                    seed=42,
                    model="mock-model",
                    prompt_hash="abc123",
                    raw_text=f"Mock response for {personas[rep].uuid} on {q.id}",
                    parsed=parsed,
                )
            )

    return responses


def create_sample_manifest() -> SampleManifest:
    """데모용 표본 매니페스트."""
    cells = [
        CellSpec(
            cell_id="C1",
            axes={"age": "30-44", "region": "수도권", "household": "자녀동거"},
            quota_survey=25,
            quota_idi=2,
        ),
        CellSpec(
            cell_id="C2",
            axes={"age": "30-44", "region": "수도권", "household": "부부"},
            quota_survey=25,
            quota_idi=1,
        ),
    ]

    assignments = [
        CellAssignment(uuid="persona-001", cell_id="C1", signal_score=0.85, price_sensitivity_score=0.4),
        CellAssignment(uuid="persona-002", cell_id="C1", signal_score=0.78, price_sensitivity_score=0.5),
        CellAssignment(uuid="persona-003", cell_id="C2", signal_score=0.92, price_sensitivity_score=0.3),
    ]

    return SampleManifest(
        seed=42,
        source="fixture",
        signals_config={"keywords": "korean-food"},
        cells_config={"age": [30, 44], "region": ["수도권"]},
        cells=cells,
        assignments=assignments,
        created_at=datetime.now(UTC).isoformat(),
    )


def create_sample_validation() -> ValidationReport:
    """데모용 검증 리포트."""
    checks = [
        ValidationCheck(
            name="distribution",
            passed=True,
            metrics={"chi_sq": 0.12, "p_value": 0.95},
            details="표본 분포가 모집단과 통계적으로 일치합니다.",
        ),
        ValidationCheck(
            name="known_truth",
            passed=True,
            metrics={"accuracy": 0.94},
            details="알려진 정답 문항 94% 정확도로 재현됨.",
        ),
        ValidationCheck(
            name="self_consistency",
            passed=True,
            metrics={"mean_kendall_tau": 0.78},
            details="반복 샘플링 간 일관성 높음 (τ > 0.6).",
        ),
    ]

    return ValidationReport(
        checks=checks,
        verdict="adopt",
        excluded_question_ids=[],
    )
