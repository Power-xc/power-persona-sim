# 저작자 표시 및 라이선스 고지

## 데이터셋 기여

본 프로젝트는 NVIDIA의 **Nemotron Personas Korea** 데이터셋을 사용합니다.

### 데이터셋 정보

| 항목 | 내용 |
|---|---|
| 이름 | Nemotron Personas Korea |
| 제공자 | NVIDIA |
| 게시일 | 2026-04-20 |
| 출처 링크 | https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea |
| 라이선스 | CC BY 4.0 |
| 규모 | 1,000,000 레코드, 약 17억 토큰 |
| 형식 | Parquet, 1.98 GB |

### CC BY 4.0 라이선스 의무사항

본 프로젝트는 CC BY 4.0에 따라 다음을 준수합니다:

1. **저작자 표시 의무**: NVIDIA와 Nemotron Personas Korea 데이터셋을 명시적으로 표시합니다.
   - 프로젝트 README.md에 "Powered by NVIDIA Nemotron" 뱃지 포함
   - 본 ATTRIBUTION.md 파일에 라이선스 및 출처 명시

2. **변경사항 명시**: 해당하는 경우 데이터를 수정하거나 변환했음을 표시합니다.
   - 현재 상태: 데이터셋 원본을 그대로 사용하며, 표본 추출과 필터링은 별도의 프로세스

3. **라이선스 사본 제공**: CC BY 4.0 라이선스 전문을 [별도 파일](https://creativecommons.org/licenses/by/4.0/)로 참조

### 통계 근거

Nemotron Personas Korea는 다음의 공개 통계를 기반으로 생성되었습니다:

- **KOSIS** (국가통계포털) — 인구통계, 지역 분포
- **대법원** — 출생연도, 성별, 이름 통계
- **국민건강보험공단** — 2024년 건강검진 데이터
- **KREI** (한국농촌경제연구원) — 식품소비행태조사(2024)

이들 통계는 모두 공개 데이터이며, CC BY 4.0 라이선스에 따라 사용됩니다.

## 프로젝트 라이선스

**power-persona-sim** 프로젝트 코드는 **MIT 라이선스** 하에 배포됩니다.

## 상표 고지

NVIDIA 및 Nemotron은 NVIDIA Corporation의 등록상표입니다. 본 프로젝트는:

- NVIDIA Corporation과 제휴하지 않았습니다.
- NVIDIA Corporation의 승인을 받지 않았습니다.
- NVIDIA Corporation의 공식 제품이 아닙니다.

본 프로젝트는 CC BY 4.0 라이선스에 따라 공개 데이터셋을 사용한 독립적인 연구 프로젝트입니다.

## 인용 방식

본 프로젝트를 인용할 때는 다음 형식을 권장합니다:

```bibtex
@dataset{nemotron_personas_korea,
  author = {NVIDIA},
  title = {Nemotron Personas Korea},
  year = {2026},
  url = {https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea},
  note = {CC BY 4.0 License}
}

@software{power_persona_sim,
  author = {Power-xc},
  title = {power-persona-sim: NVIDIA Nemotron Personas Korea 기반 소비자 조사 시뮬레이터},
  year = {2026},
  url = {https://github.com/Power-xc/power-persona-sim},
  note = {MIT License}
}
```

## 변경 및 배포 조건

CC BY 4.0의 요구사항:

1. 본 데이터셋을 사용하여 파생물을 만들 경우, 원본의 저작자 정보를 명시해야 합니다.
2. 라이선스 조건을 함께 표시해야 합니다.
3. 변경사항을 명시해야 합니다.
4. 상업적 이용이 가능하나, 상기 조건을 모두 준수해야 합니다.

---

**마지막 업데이트**: 2026-07-28
