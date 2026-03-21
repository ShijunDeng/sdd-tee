# AgentCube documentation site

This directory contains a [Docusaurus](https://docusaurus.io/) project that publishes user-facing documentation for **AgentCube**, the Volcano subproject for Kubernetes-native AI agent workloads.

## Prerequisites

- Node.js **18** or newer
- npm **9**+ (or compatible package manager)

## Commands

```bash
cd docs/agentcube
npm install
npm run start      # local dev server — http://localhost:3000
npm run build      # static build → build/
npm run serve      # preview production build
npm run deploy     # publish (configure GIT_USER and hosting first)
```

## Content layout

| Path | Purpose |
|------|---------|
| `docs/` | Markdown documentation (intro, architecture, guides, tutorials) |
| `src/pages/` | Custom React pages (homepage) |
| `src/components/` | Shared React components |
| `blog/` | Release notes and articles |
| `static/` | Static assets (logos, `.nojekyll` for GitHub Pages) |

Design deep-dives and internal proposals live under the repository’s `docs/design/` directory (outside this site tree). Link to them from docs where helpful.

## Configuration

- `docusaurus.config.ts` — site metadata, navbar, footer, presets
- `sidebars.ts` — documentation sidebar structure

Update `url` and `baseUrl` in `docusaurus.config.ts` to match your hosting path before running `npm run deploy`.
