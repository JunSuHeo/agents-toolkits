---
name: parallel-development
description: 겹치지 않는 작업을 분리하여 Git worktree로 병렬 개발한다.
metadata:
  toolkit-dependencies: "task-decomposition,handoff"
---

# parallel-development

겹치지 않는 작업을 분리하여 Git worktree로 병렬 개발한다.

## 입력과 선행 조건

- 작업 ID, 기준 커밋, 소유 역할과 파일 경계
- 작업 분해 결과와 독립 경로, Git 상태를 확인한다.

## 적용 범위와 도구

할당된 프로젝트와 명시적으로 허용된 범위에서만 적용한다. 사용 도구는 agent-toolkit worktree, 로컬 Git, 승인된 테스트다.

## 절차

1. 작업별 브랜치와 입력·출력·경로·금지 작업을 명시한다.
2. 독립 작업만 별도 worktree에서 수행하고 변경 및 테스트를 기록한다.
3. 파일 경계와 충돌을 검토하며 통합 순서대로 합친 후 전체 검증한다.

## 출력과 검증

작업별 handoff, 브랜치, 검증과 통합 결과. 미커밋 파일과 임시 데이터가 보존되며 통합 후 필수 테스트가 통과한다.

## 실패 처리와 제한

쓰기가 겹치면 통합을 잠시 멈추고 한 소유자의 순차 작업으로 바꾼다. 프로젝트의 보안 및 승인 정책을 따른다. 선행 Skill은 task-decomposition, handoff이다.
