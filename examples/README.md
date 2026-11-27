# 검증용 예제

Toolkit 저장소에서 다음처럼 실행합니다.

```bash
uv run agent-toolkit init --path ./sandbox-web --config examples/web-service.yml --dry-run
```

| 시나리오 | 구성 파일 또는 fixture | 검증 대상 |
| --- | --- | --- |
| A 일반 웹서비스 | [web-service.yml](web-service.yml) | Next.js, TypeScript, Supabase, CI를 가정한 검증 범위 및 Codex·Claude Code 생성 |
| B AI 에이전트 서비스 | [ai-agent.yml](ai-agent.yml) | Python, FastAPI, LangGraph, PostgreSQL과 평가·프롬프트 테스트 지침 |
| C 대량 처리 | [data-pipeline.yml](data-pipeline.yml) | Rust, Oracle, Linux, 메모리 및 처리량 기준 |
| D 업무 백엔드 | [backend-api.yml](backend-api.yml) | Java, Spring Boot, Oracle, Docker |
| E 소규모 자동화 | [automation.yml](automation.yml) | Python, 단일 역할과 최소 구성 |
| F 기존 프로젝트 | [existing/](existing/) | 원본 지침, 코드, CI, 테스트 및 사용자 파일 보호와 업데이트 |

F는 다른 디렉터리로 복사한 후 그 위치에서 `agent-toolkit adopt --tools codex,claude`로 조사와 계획을 보고 `--apply`로 적용합니다. A~E는 구성 생성용이며 애플리케이션 소스나 CI 실행 환경을 설치하지 않습니다.
