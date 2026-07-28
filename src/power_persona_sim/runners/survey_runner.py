"""설문 배치 실행 엔진.

재현성 규약: run_id와 파생 seed는 전부 입력값의 해시로만 결정된다.
프로세스·실행 시점·호출 순서가 달라도 같은 입력이면 같은 실행이다 (PREREG 전제).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ..contracts import (
    PersonaRecord,
    Question,
    QuestionType,
    ResponseRecord,
    RunConfig,
    Survey,
)
from .adapters import LLMAdapter


@dataclass(frozen=True)
class PersonaNarrative:
    """프롬프트에 실을 서사 블록 — 케이스가 바뀌면 이것이 바뀐다.

    식품 케이스는 식생활 서사를, B2B 도구 케이스는 직무 서사를 실어야 한다.
    조사 주제와 무관한 서사를 실으면 그 자체가 응답을 오염시키므로,
    카테고리 설정(configs/signals/*.yaml)이 이 블록의 소유자다.
    """

    fields: tuple[tuple[str, str], ...]  # (라벨, 컬럼명)
    consistency_rule: str

    def render(self, persona: PersonaRecord) -> str:
        lines = []
        for label, column in self.fields:
            value = getattr(persona, column, None)
            if value is None:
                value = persona.raw.get(column)
            if isinstance(value, (list, tuple)):
                value = ", ".join(str(v) for v in value)
            text = str(value or "").strip()
            if text:
                lines.append(f"[{label}] {text}")
        return "\n".join(lines)


#: 기존 동작(갈비찜 케이스)을 그대로 보존하는 기본값.
DEFAULT_NARRATIVE = PersonaNarrative(
    fields=(
        ("인물", "persona"),
        ("식생활", "culinary_persona"),
        ("가족", "family_persona"),
        ("관심사", "hobbies_and_interests"),
    ),
    consistency_rule="위 식생활 서사와 모순되는 답을 하지 마세요.",
)


def assemble_system_prompt(
    persona: PersonaRecord,
    condition: str = "natural",
    narrative: PersonaNarrative | None = None,
) -> str:
    """페르소나 시스템 프롬프트 조립 (PROJECT-BRIEF §5.2).

    condition="forced_unaware"면 미인지 조건을 강제 주입한다 —
    인지/미인지 집단을 분리 수집해 K3(인지율) 오염을 막기 위한 장치.
    narrative를 주면 서사 블록과 일관성 규칙을 케이스에 맞게 교체한다.
    """
    narrative = narrative or DEFAULT_NARRATIVE
    prompt = f"""당신은 아래 인물 본인입니다. 조사에 응답하는 실제 응답자로서 답하세요.

[기본] {persona.sex}, {persona.age}세, {persona.marital_status}, {persona.family_type},
       {persona.housing_type} 거주, {persona.province} {persona.district}, 직업: {persona.occupation}
{narrative.render(persona)}

규칙:
- {narrative.consistency_rule}
- 모르는 브랜드는 솔직히 "모른다"고 답하세요. 아는 척하지 마세요.
- 마케팅 용어가 아니라 본인이 실제 쓰는 말투로 답하세요.
- 답을 꾸며내지 말고, 경험이 없으면 없다고 하세요.
"""
    if condition == "forced_unaware":
        prompt += (
            "\n[특수 조건] 아래 질문에서 언급되는 브랜드는 들어본 적도 없습니다. "
            "이 상태를 기억하세요.\n"
        )
    return prompt


def derive_seed(base_seed: int, persona_uuid: str, question_id: str, repetition: int) -> int:
    """(persona, question, repetition)별 결정적 파생 seed.

    파이썬 내장 hash()는 프로세스마다 솔트가 달라 재현성이 깨지므로 sha256을 쓴다.
    """
    digest = hashlib.sha256(
        f"{base_seed}|{persona_uuid}|{question_id}|{repetition}".encode()
    ).digest()
    return int.from_bytes(digest[:4], "big")


def build_run_id(survey: Survey, config: RunConfig) -> str:
    """결정적 run_id — 같은 설문·설정이면 같은 실행으로 취급해 resume이 가능하다."""
    return (
        f"{survey.id}-{config.model}-s{config.seed}"
        f"-{config.prompt_version}-{config.awareness_condition}"
    )


def calculate_prompt_hash(system_prompt: str, question_text: str, model: str, seed: int) -> str:
    """프롬프트 fingerprint (PREREG 대조용)."""
    combined = f"{system_prompt}||{question_text}||{model}||{seed}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def render_question(question: Question) -> str:
    """응답자에게 실제로 보낼 문항 텍스트.

    문항 본문만 보내면 선택지가 있는 문항도 응답자는 선택지를 못 본다. 그러면
    돌아오는 것은 '선택'이 아니라 자유 서술이고, parse_response는 그 서술에서
    우연히 겹치는 낱말을 골라 선택지인 척 기록한다 — 조용히 오염된 데이터가 된다.
    응답 형식 지시도 함께 붙인다. 지시가 없으면 소형 모델은 문단으로 답한다.
    """
    config = getattr(question, "config", None) or {}
    parts = [question.text]

    if question.options:
        parts.append("\n선택지:\n" + "\n".join(f"- {opt}" for opt in question.options))

    if question.qtype == QuestionType.SINGLE:
        parts.append("\n선택지 중 하나만 골라, 그 문구만 그대로 답하세요. 설명은 쓰지 마세요.")
    elif question.qtype == QuestionType.MULTI:
        parts.append(
            "\n해당하는 선택지를 모두 골라, 그 문구만 쉼표로 구분해 나열하세요. 설명은 쓰지 마세요."
        )
    elif question.qtype == QuestionType.RANK:
        top_n = config.get("top_n") or len(question.options)
        parts.append(
            f"\n선택지 중 {top_n}개를 골라 순위 순서대로 쉼표로 구분해 나열하세요. "
            "그 문구만 쓰고 설명은 쓰지 마세요."
        )
    elif question.qtype == QuestionType.MAXDIFF:
        parts.append(
            "\n가장 중요한 것 하나와 가장 덜 중요한 것 하나를 골라 "
            "'가장중요: <문구>, 가장덜중요: <문구>' 형식으로만 답하세요."
        )
    elif question.qtype == QuestionType.SCALE:
        points = question.scale_points or 7
        low = config.get("anchor_low", "전혀 아니다")
        high = config.get("anchor_high", "매우 그렇다")
        parts.append(f"\n1({low})부터 {points}({high})까지 중 숫자 하나만 답하세요.")
    elif question.qtype == QuestionType.NUMERIC:
        unit = config.get("unit", "")
        parts.append(f"\n숫자 하나만 답하세요{f' (단위: {unit})' if unit else ''}. 설명은 쓰지 마세요.")
    elif question.qtype == QuestionType.OPEN:
        parts.append("\n한두 문장으로 짧게 답하세요.")

    return "".join(parts)


def _ordered_options(raw_text: str, options: list[str]) -> list[str]:
    """응답 안에 등장한 선택지를 등장 순서대로. 중복은 첫 등장만 남긴다."""
    found = [(raw_text.find(opt), opt) for opt in options if opt in raw_text]
    return [opt for _, opt in sorted(found)]


def _first_option(raw_text: str, options: list[str], *, after: str) -> str | None:
    """`after` 표지 뒤에서 처음 나오는 선택지. 표지가 없으면 None."""
    marker = raw_text.find(after)
    if marker < 0:
        return None
    tail = raw_text[marker + len(after) :]
    found = [(tail.find(opt), opt) for opt in options if opt in tail]
    return min(found)[1] if found else None


def parse_response(
    raw_text: str, qtype: QuestionType, options: list[str] | None = None
) -> dict | list | str | int | float:
    """응답 텍스트를 문항 유형별로 파싱."""
    if qtype in (QuestionType.SINGLE, QuestionType.MULTI):
        if not options:
            return raw_text
        matched = [opt for opt in options if opt.lower() in raw_text.lower()]
        if qtype == QuestionType.SINGLE:
            return matched[0] if matched else raw_text
        return matched if matched else [x.strip() for x in raw_text.split(",")]

    if qtype == QuestionType.RANK:
        # 공백으로 쪼개면 '숫자가 들어 있는 표'가 네 조각이 된다 — 순위 자체가 사라진다.
        # 선택지를 알고 있으면 등장 순서대로 선택지를 되찾는 것이 유일하게 옳은 해석이다.
        if options:
            return _ordered_options(raw_text, options)
        return [x.strip() for x in raw_text.split(",") if x.strip()]

    if qtype == QuestionType.MAXDIFF:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass
        if options:
            best = _first_option(raw_text, options, after="가장중요")
            worst = _first_option(raw_text, options, after="가장덜중요")
            picked = [x for x in (best, worst) if x]
            if picked:
                return picked
            return _ordered_options(raw_text, options)
        return [x.strip() for x in raw_text.split(",") if x.strip()]

    if qtype == QuestionType.VAN_WESTENDORP:
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        numbers = re.findall(r"\d+", raw_text)
        if len(numbers) >= 4:
            return {
                "too_cheap": int(numbers[0]),
                "cheap": int(numbers[1]),
                "expensive": int(numbers[2]),
                "too_expensive": int(numbers[3]),
            }
        return raw_text

    if qtype in (QuestionType.SCALE, QuestionType.NUMERIC):
        match = re.search(r"\d+", raw_text)
        return int(match.group()) if match else raw_text

    return raw_text  # OPEN


def load_responses(path: Path) -> list[ResponseRecord]:
    """results/raw jsonl 로그 → ResponseRecord 목록. validate·report 커맨드의 입력."""
    records: list[ResponseRecord] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(ResponseRecord(**json.loads(line)))
    return records


class SurveyRunner:
    """배치 설문 실행기.

    log_dir을 주면 results/raw 스타일 jsonl에 응답을 append하고,
    같은 run_id로 재실행 시 완료분을 건너뛴다(resume).
    """

    def __init__(
        self,
        adapter: LLMAdapter,
        log_dir: Path | None = None,
        narrative: PersonaNarrative | None = None,
    ):
        self.adapter = adapter
        self.log_dir = Path(log_dir) if log_dir else None
        self.narrative = narrative or DEFAULT_NARRATIVE

    def _log_path(self, run_id: str) -> Path | None:
        if not self.log_dir:
            return None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self.log_dir / f"{run_id}.jsonl"

    @staticmethod
    def _load_completed(log_path: Path) -> tuple[set[tuple[str, str, int]], list[ResponseRecord]]:
        records = load_responses(log_path)
        completed = {(r.persona_uuid, r.question_id, r.repetition) for r in records}
        return completed, records

    def run_survey(
        self, survey: Survey, personas: list[PersonaRecord], config: RunConfig
    ) -> list[ResponseRecord]:
        """(persona × question × repetition) 전개 배치 실행.

        어댑터 에러는 삼키지 않고 전파한다 — [ERROR] 텍스트가 정상 응답인 척
        분석 파이프라인에 섞이는 것이 실행 중단보다 나쁘기 때문.
        """
        run_id = build_run_id(survey, config)
        log_path = self._log_path(run_id)
        completed, responses = (
            self._load_completed(log_path) if log_path else (set(), [])
        )

        log_file = log_path.open("a", encoding="utf-8") if log_path else None
        try:
            for persona in personas:
                system_prompt = assemble_system_prompt(
                    persona, config.awareness_condition, self.narrative
                )
                for question in survey.questions:
                    user_message = render_question(question)
                    for rep in range(config.repetitions):
                        if (persona.uuid, question.id, rep) in completed:
                            continue

                        seed = derive_seed(config.seed, persona.uuid, question.id, rep)
                        raw_text = self.adapter.generate(
                            system_prompt=system_prompt,
                            user_message=user_message,
                            temperature=config.temperature,
                            seed=seed,
                        )
                        record = ResponseRecord(
                            run_id=run_id,
                            persona_uuid=persona.uuid,
                            question_id=question.id,
                            repetition=rep,
                            seed=seed,
                            model=config.model,
                            prompt_hash=calculate_prompt_hash(
                                system_prompt, user_message, config.model, seed
                            ),
                            raw_text=raw_text,
                            parsed=parse_response(
                                raw_text, question.qtype, options=question.options or None
                            ),
                        )
                        responses.append(record)
                        if log_file:
                            log_file.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
                            log_file.flush()
        finally:
            if log_file:
                log_file.close()
        return responses
