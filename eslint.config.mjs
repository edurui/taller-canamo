import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig(
  {
    ignores: [
      'build/**',
      'dist/**',
      'node_modules/**',
      'private-reference/**',
      'reports/**',
      'src-tauri/target/**',
      'backend/**',
      'tools/**',
    ],
  },
  {
    files: ['frontend/**/*.{ts,tsx}', 'e2e/**/*.ts', '*.ts'],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      // RPC records currently use Row/any. Strict tsc remains mandatory; changing
      // that public contract belongs to a separate typed-API migration.
      '@typescript-eslint/no-explicit-any': 'off',
      // Object rest intentionally omits transient/read-only fields before RPC.
      '@typescript-eslint/no-unused-vars': ['error', { ignoreRestSiblings: true }],
    },
  },
  {
    files: ['scripts/*.{js,cjs,mjs}', '*.mjs'],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
  {
    files: ['public/*.js'],
    extends: [js.configs.recommended],
    languageOptions: { globals: { ...globals.browser, ...globals.audioWorklet } },
  },
);
