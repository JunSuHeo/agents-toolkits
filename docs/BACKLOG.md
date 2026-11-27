# 구현 상태와 로드맵

| 단계 | 상태 | 근거 |
| --- | --- | --- |
| 0 조사 및 설계 | 구현 | [조사](RESEARCH.md), [요구사항](SPEC.md), [결정](DECISIONS.md), [설계](ARCHITECTURE.md) |
| 1 공통 개발 표준 | 구현 | Core, 10개 Profile, 17개 Stack, 12개 역할, 워크플로, 문서 템플릿, JSON Schema |
| 2 핵심 Skills | 구현 | 10개 Skill, 설명 검색, 명시적 선택과 의존성 해석 |
| 3 초기화 엔진 | 구현 | `init`, `inspect`, `adopt`, 구성 검증, 충돌 제어 |
| 4 Adapters | 구현 | Codex와 Claude Code 역할, Codex·Claude Code·Grok Build Skills, Generic 및 Grok의 공통 역할 |
| 5 버전 및 검증 | 구현 | Lock, 상태, 변경 비교, 복구, Gate, 패키지와 CI |
| 6 협업 | 구현 | 규모별 역할 계획, 작업별 인수인계, Git worktree, 통합 및 독립 검증 절차 |

검증 범위와 환경은 [TESTING](TESTING.md)에 기록한다.

## 향후 작업

- 공식 클라이언트 버전과 도구별 실세션 로딩을 자동 검증한다. 확인 가능한 Grok 네이티브 역할 형식을 실설치본에서 검증한다.
- Docker worker에서 파일·네트워크 권한을 분리하고 승인된 도구 호출만 노출한다.
- 스택 감지와 CI 증거 수집을 모노레포에 확장한다.
- 외부 Skills의 신뢰 검토와 검증 설치를 별도 명령으로 제공한다.
- 집계 가능한 컨텍스트·호출 비용 및 반복 오류의 비식별 개선 제안에 승인 단계를 둔다.

0.1.1에 하위 경로 탐색, Claude 지침 연결, npm 스택 감지 및 Lock 기준 검증을 반영했다.

0.1.2에 `inspect --suggest-rules`의 프로젝트 규칙 초안과 근거 표시를 반영했다.
