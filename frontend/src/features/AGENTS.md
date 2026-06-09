# Features (features)

## Purpose

Feature modules, each owning its domain: store (Pinia), API client, and UI components. Features are self-contained and communicate via stores.

## Ownership

Frontend team owns feature implementation, state management, and UI components.

## Local Contracts

- **Feature structure**: `store.ts`, `api.ts`, `ui/` components
- **State**: Pinia store per feature, no cross-feature state access
- **API calls**: All API calls via store actions, never in components
- **Types**: Import shared types from `shared/types.ts`
- **Composables**: Extract reusable logic to composables
- **Events**: Use Vue events for parent-child communication, stores for sibling communication

## Work Guidance

- **New feature**: Create directory with `store.ts`, `api.ts`, `ui/` subdirectory
- **Store actions**: Async actions for API calls, sync actions for local state
- **Error handling**: Catch API errors in actions, set error state
- **Loading states**: Track loading in store, display in UI
- **Optimistic updates**: Update UI immediately, rollback on error
- **Testing**: Test stores and composables, not components

## Verification

Feature tests in `src/__tests__/features/`

## Child DOX Index

- `analysis/` - Document analysis and parsing
- `chunking/` - Chunk management and editing
- `document/` - Document upload and management
- `feature-flags/` - Feature flag store
- `history/` - Navigation history
- `settings/` - User settings and preferences
