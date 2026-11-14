# Main-process features

One file per feature, `<name>.ts`, default-exporting `defineMainFeature({ id, setup(ctx) })`.
Discovered automatically by `src/main/index.ts`. See `../context.ts` for everything `ctx` offers
(createWindow, handle, broadcast, onSignal, engine.onOpen…).
