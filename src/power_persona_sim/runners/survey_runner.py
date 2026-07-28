"""설문 배치 실행 엔진.

재현성 규약: run_id와 파생 seed는 전부 입력값의 해시로만 결정된다.
프로세스·실행 시점·호출 순서가 달라도 같은 입력이면 같은 실행이다 (PREREG 전제).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from ..contracts import PersonaRecord, QuestionType, ResponseRecord, RunConfig, Survey
from .adapters import LLMAdapter


def assemble_system_prompt(persona: PersonaRecord, condition: str = "natural") -> str:
    """페르소나 시스템 프롬프트 조립 (PROJECT-BRIEF §5.2).

    condition="forced_unaware"면 미인지 조건을 강제 주입한다 —
    인지/미인지 집단을 분리 수집해 K3(인지율) 오염을 막기 위한 장치.
    """
    prompt = f"""당신은 아래 인물 본인입니다. 조사에 응답하는 실제 소비자로서 답하세요.

[기본] {persona.sex}, {persona.age}세, {persona.marital_status}, {persona.family_type},
       {persona.housing_type} 거주, {persona.province} {persona.district}, 직업: {persona.occupation}
[인물] {persona.persona}
[식생활] {persona.culinary_persona}
[가족]   {persona.family_persona}
[관심사] {persona.hobbies_and_interests}

규칙:
- 위 식생활 서사와 모순되는 답을 하지 마세요.
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
        return [x.strip() for x in raw_text.replace(",", " ").split()]

    if qtype == QuestionType.MAXDIFF:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return [x.strip() for x in raw_text.split(",")]

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


class SurveyRunner:
    """배치 설문 실행기.

    log_dir을 주면 results/raw 스타일 jsonl에 응답을 append하고,
    같은 run_id로 재실행 시 완료분을 건너뛴다(resume).
    """

    def __init__(self, adapter: LLMAdapter, log_dir: Path | None = None):
        self.adapter = adapter
        self.log_dir = Path(log_dir) if log_dir else None

    def _log_path(self, run_id: str) -> Path | None:
        if not self.log_dir:
            return None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self.log_dir / f"{run_id}.jsonl"

    @staticmethod
    def _load_completed(log_path: Path) -> tuple[set[tuple[str, str, int]], list[ResponseRecord]]:
        completed: set[tuple[str, str, int]] = set()
        records: list[ResponseRecord] = []
        if not log_path.exists():
            return completed, records
        with log_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                record = ResponseRecord(**data)
                completed.add((record.persona_uuid, record.question_id, record.repetition))
                records.append(record)
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
                system_prompt = assemble_system_prompt(persona, config.awareness_condition)
                for question in survey.questions:
                    for rep in range(config.repetitions):
                        if (persona.uuid, question.id, rep) in completed:
                            continue

                        seed = derive_seed(config.seed, persona.uuid, question.id, rep)
                        raw_text = self.adapter.generate(
                            system_prompt=system_prompt,
                            user_message=question.text,
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
                                system_prompt, question.text, config.model, seed
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
