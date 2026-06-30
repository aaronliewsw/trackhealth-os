# TrackHealth OS Web

Vite + React + TypeScript shell for Slice 5. The dev and preview servers mock
`GET /api/state` from `../tests/fixtures/contract/state.json`, so no backend is
required.

## Install

```sh
npm install
```

## Run With Mock

```sh
npm run dev
```

Open the URL printed by Vite. Requests to `/api/state` are served by the Vite
contract mock.

## Production Build

```sh
npm run build
```

To inspect the built app with the same mock active:

```sh
npm run preview
```
