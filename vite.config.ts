import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  plugins: [{
    name: 'canamo-local-session-bootstrap',
    transformIndexHtml: {
      order: 'post',
      handler: () => [{tag: 'script', attrs: {src: './runtime.js'}, injectTo: 'head-prepend'}],
    },
  }],
  build: { outDir: 'dist', emptyOutDir: true },
});
