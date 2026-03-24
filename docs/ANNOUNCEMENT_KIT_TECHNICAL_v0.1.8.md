# 6X-Protocol Studio v0.1.8 Announcement Kit (Technical)

Release URL: https://github.com/synryzen/6X-Protocol/releases/tag/v0.1.8  
Repo URL: https://github.com/synryzen/6X-Protocol  
Docs URL: https://synryzen.github.io/6X-Protocol/

---

## 1) Technical GitHub/Dev Post

```md
6X-Protocol Studio v0.1.8 is out.

This release focuses on local-first workflow execution plus a Docker self-hosted web path with verified runtime behavior.

### Runtime/API
- Graph-aware execution traversal (nodes/edges)
- Retry/backoff/timeout policies
- Cancel/retry/retry-from-failed-node run controls
- Approval-gate pause/resume flow
- Timeline/log query endpoints

### Builder
- Node types: Trigger / Action / AI / Condition
- Node-level behavior editor and execution defaults
- Web visual graph stage now supports direct wire dragging (output port -> input port) with duplicate-link protection

### Self-hosted stack
- Docker compose services: API + worker + web + Postgres + Redis
- Smoke validated end-to-end via `./scripts/test_docker_web.sh`

### Packaging
- Linux artifacts: .deb, portable tar.gz, AppImage, Flatpak, checksums

Release: https://github.com/synryzen/6X-Protocol/releases/tag/v0.1.8
Repo: https://github.com/synryzen/6X-Protocol
```

---

## 2) Technical X / Twitter

```text
6X-Protocol Studio v0.1.8 shipped.

Linux-native local-first automation + Docker self-hosted web path.

Highlights:
- Graph-aware runtime
- Retry/backoff/timeout + retry-from-failed
- Approval-gate resume flow
- Web canvas direct wire drag linking

Release: https://github.com/synryzen/6X-Protocol/releases/tag/v0.1.8
Repo: https://github.com/synryzen/6X-Protocol

#opensource #selfhosted #linux #automation #devtools
```

---

## 3) Technical Reddit / HN Body

```text
I released 6X-Protocol Studio v0.1.8 (open source).

Primary goal: local-first automation with a visual workflow builder and explicit execution controls.

What’s in the current build:
- Graph-aware execution engine
- Retry/backoff/timeout controls
- Cancel/retry/retry-from-failed-node
- Approval gate pause/resume support
- Timeline/log query APIs
- Docker self-hosted stack (API, worker, web, Postgres, Redis)
- Web visual canvas with direct wire dragging (output->input)

Release: https://github.com/synryzen/6X-Protocol/releases/tag/v0.1.8
Repo: https://github.com/synryzen/6X-Protocol
Docs: https://synryzen.github.io/6X-Protocol/

Interested in feedback on runtime reliability, connector ergonomics, and canvas UX.
```

---

## 4) Quick Technical Replies

For “How stable is it?”
```text
Current release is validated with unit tests + automated Docker smoke tests covering workflow/runs, control endpoints, timeline/log queries, integrations, bots, and settings flows.
```

For “How is this different from cloud-first tools?”
```text
The core approach is local-first Linux desktop workflow automation with optional self-hosted Docker web access, rather than a cloud-only default.
```
