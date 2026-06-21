# Aksh Ship — idea to deploy (functional)

Omni work modes control scope. User sees only **Omni**; experts route in the background.

## Work modes

| Mode | Use case |
|------|----------|
| **ship** | Plan → build → deploy kit (default for new apps) |
| **fix** | Bug fix only — minimal patches |
| **extend** | Add features — no unrelated refactors |
| **guard** | Security scan + report — no edits unless asked |
| **explain** | Read-only explanations |
| **deploy** | Docker, compose, K8s templates, DEPLOY.md |
| **auto** | Omni detects from your message |

## Normal user (Aksh Cloud)

1. Sign up → Dashboard → API key  
2. Studio → New cloud project or upload zip  
3. Pick work mode → Chat or Agent tab  
4. **Deploy kit** button → generates Dockerfile, docker-compose, `deploy/k8s/`, DEPLOY.md  
5. **Security scan** button → secrets + risky pattern report  

## Enterprise (on-prem)

- Set agent `project_root` to your Git checkout path on the server  
- Code stays on your network; Omni routes experts locally  
- Use **fix / extend / guard** modes for scoped professional work  
- Deploy kit generates artifacts for **your** CI/CD (Jenkins, Argo, internal K8s)

## API

```http
POST /v1/chat
{ "message": "...", "work_mode": "fix", "project_id": "uuid", "thread_id": "uuid" }

POST /v1/agent/run
{ "task": "...", "work_mode": "deploy", "project_id": "uuid" }

POST /saas/v1/projects/{id}/deploy-kit
POST /saas/v1/projects/{id}/security-scan
```

## E2E Networks deploy

See [E2E_DEPLOY.md](./E2E_DEPLOY.md). After deploy kit:

```bash
docker compose up -d --build
```

Target: Delhi API VM + optional Chennai GPU for Omni inference.
