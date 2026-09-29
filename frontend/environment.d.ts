export {};
declare global {
  interface Window {
    __CANAMO_DEV_TOKEN__?: string;
    __TAURI__?: {core: {invoke<T = any>(command: string, args?: Record<string, unknown>): Promise<T>}};
  }
}
