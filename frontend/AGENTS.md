# Frontend SPA (frontend)

## Purpose

Vue 3 single-page application providing document upload, parsing configuration, results visualization, chunking, ingestion, search, and chat UI. Feature-based architecture with Pinia stores.

## Ownership

Frontend team owns all TypeScript/Vue code, UI components, routing, state management, and API client layer.

## Local Contracts

- **Architecture**: Feature-based. Each feature owns store, API client, and UI components
- **State management**: Pinia stores per feature, no global state
- **Routing**: Vue Router with lazy-loaded pages
- **API client**: Fetch wrapper in `shared/api/http.ts`, camelCase JSON
- **Styling**: Custom CSS with CSS variables for theming, no component library
- **TypeScript**: Strict mode, shared types in `shared/types.ts`
- **Testing**: Vitest with 156+ tests, all must pass before merge

## Work Guidance

- **Type-check**: `npm run type-check` before commit
- **Linting**: `npx eslint src/ --fix` before commit
- **Formatting**: `npx prettier --write src/` before commit
- **Components**: Keep components focused, extract shared logic to composables
- **API calls**: All API calls via Pinia store actions, never directly in components
- **Error handling**: Display user-friendly messages, log technical details
- **i18n**: Use `shared/i18n.ts` for all user-facing strings (FR/EN)
- **Feature flags**: Check feature availability via `features/feature-flags/store.ts`

## Verification

```bash
cd frontend
npm run type-check
npx eslint src/
npx prettier --check src/
npm run test:run
```

## Child DOX Index

- `src/app/` - App shell, router, global styles
- `src/pages/` - Route-level page components
- `src/features/` - Feature modules (analysis, chunking, document, etc.)
- `src/shared/` - Cross-feature utilities (types, i18n, API client)
