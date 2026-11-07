# Qasida dynamic registry — deploy

This is a dynamic registry: clients publish with POST, not git push.
It is a single Python file with no dependencies
(`forge_lang/registry_server.py`).

The server reads its settings from the environment, so no secret
lives in a command line: `PORT` (default 8765) and
`FORGE_REGISTRY_TOKEN` (if unset, the registry is open and
anyone can publish; if set, publishing requires
`Authorization: Bearer <token>`). CLI flags `--port` / `--token`
still override the environment. `GET /` and `GET /health`
return `{"ok": true}` for health checks.

## Docker (any VPS with Docker)

    docker build -t forge-registry -f registry/Dockerfile .
    docker run -d -p 8765:8765 -e FORGE_REGISTRY_TOKEN=secret \
      -v forge-data:/data forge-registry

## Render (Blueprint, one click)

Dashboard -> New -> Blueprint, point it at this repo
(`registry/render.yaml`). Set `FORGE_REGISTRY_TOKEN` in the
dashboard when prompted; Render assigns `PORT` itself.

Warning: a free Render instance has an ephemeral disk, so
published packages vanish on restart/redeploy. For the real
public registry, attach a persistent disk (paid instance) or
use Fly / a VPS below.

## Fly.io (persistent volume)

From the repo root, in order:

    fly launch --no-deploy
    fly volumes create qasida_data --size 1 --region iad
    fly secrets set FORGE_REGISTRY_TOKEN=secret
    fly deploy --config registry/fly.toml --dockerfile registry/Dockerfile

The volume persists published packages across deploys. If `fly
launch` suggested a different app name, change the `app` line in
`registry/fly.toml` to match.

## VPS without Docker (systemd)

    # clone the repo to /opt/qasida (or edit WorkingDirectory)
    sudo mkdir -p /var/lib/qasida-registry
    sudo chown nobody:nogroup /var/lib/qasida-registry
    # optional token: FORGE_REGISTRY_TOKEN=secret in /etc/qasida-registry.env
    sudo cp registry/qasida-registry.service /etc/systemd/system/
    sudo systemctl daemon-reload && sudo systemctl enable --now qasida-registry

Put nginx/Caddy with HTTPS in front for public use — the server
itself is HTTP only, and the Bearer token must not travel over
plain HTTP on the public internet.

## Clients

Once the server is up at `https://<your-host>` (or
`http://<your-host>:8765` for a local test):

    qasida pkg publish-remote https://<your-host> --token secret
    qasida pkg add-remote https://<your-host> checks@0.1.0
    qasida pkg list-remote https://<your-host>

## What is NOT provided here

A host. This repo gives you the server and the deploy files, not
a VPS, Render account, or domain. Central hosting means you run
the above on a host you control, then share its URL.
