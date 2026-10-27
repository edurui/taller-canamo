export {};
declare global {
  interface Window {
    __CANAMO_DEV_TOKEN__?: string;
    __TAURI__?: {
      core: {invoke<T = any>(command: string, args?: Record<string, unknown>): Promise<T>};
      event?: {listen<T>(name: string, handler: (event: {payload: T}) => void): Promise<() => void>};
    };
  }
}
