# Example: Verasure

보험 정보를 기록하고 확인하는 작은 학습용 프로젝트입니다.
`AGENTS.md`의 Technical Defaults를 그대로 쓰고, MVP 범위만 여기서 정합니다.

Target repository는 사용자가 지정합니다. Harness 폴더 밖에 두고, `/tmp` 대신
재부팅 후에도 남는 경로를 권장합니다.

## P0 MVP

- static `index.html` 첫 화면
- 보험 정보 등록
- 보험 정보 목록
- 보험 정보 상세
- 상태 표시: `CONFIRMED`, `UNKNOWN`, `NEEDS_REVIEW`

## 세션 순서

1. Spring Boot 프로젝트 생성 + 첫 화면
2. 도메인 모델과 상태 enum
3. 보험 정보 등록
4. 보험 정보 목록
5. 상세 보기
6. 검증과 오류 메시지
7. 테스트와 정리

## P0에서 제외

`AGENTS.md`의 기본 제외 항목에 더해:

- 보험 추천 및 판단 자동화
- PDF 약관 업로드와 OCR
- RAG 기반 질의응답

이 기능들은 P0 이후에 별도로 논의합니다.
