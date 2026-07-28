"""테스트용 간단한 fixture 페르소나."""

from power_persona_sim.contracts import PersonaRecord

# 테스트용 미니 페르소나 2종
TEST_PERSONAS = [
    PersonaRecord(
        uuid="test-persona-001",
        sex="남자",
        age=45,
        marital_status="배우자있음",
        family_type="배우자와 거주",
        housing_type="아파트",
        education_level="4년제 대학교",
        occupation="회계 사무원",
        district="서울-서초구",
        province="서울",
        persona="김철수 씨는 서울 서초구에서 회계 일을 하며 살아온 중년 가장입니다.",
        culinary_persona="주말에 가족과 함께 외식을 즐기며, 명절에는 직접 갈비찜을 준비합니다.",
        family_persona="아내와 중학생 자녀 1명과 함께 삽니다.",
        hobbies_and_interests="주말 등산, 가족 여행, 요리",
        raw={}
    ),
    PersonaRecord(
        uuid="test-persona-002",
        sex="여자",
        age=52,
        marital_status="배우자있음",
        family_type="배우자와 거주",
        housing_type="단독주택",
        education_level="고등학교",
        occupation="음식점 사무원",
        district="광주-서구",
        province="광주",
        persona="이영희 씨는 광주에서 평생 식품 관련 일을 해온 중년 여성입니다.",
        culinary_persona="매주 직접 반찬을 만들며, 갈비찜은 명절 잔치 음식으로 생각합니다.",
        family_persona="남편과 함께 거주하며 자녀는 이미 성인입니다.",
        hobbies_and_interests="시장 장보기, 전통 요리, 종교 활동",
        raw={}
    ),
]


def get_test_personas() -> list[PersonaRecord]:
    """테스트 페르소나 반환."""
    return TEST_PERSONAS
