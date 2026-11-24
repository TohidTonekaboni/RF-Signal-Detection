import reactHooks from 'eslint-plugin-react-hooks'
import jsxA11y from 'eslint-plugin-jsx-a11y'

// Flags physical-direction Tailwind classes (ml-/mr-/pl-/pr-/left-/right-/text-left/text-right)
const physical = /(^|[\s"'`:])(-?)(ml|mr|pl|pr|left|right)-[\w[]|text-(left|right)\b/

export default [
  { ignores: ['dist', 'node_modules'] },
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: { ecmaVersion: 2023, sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { window: 'readonly', document: 'readonly', localStorage: 'readonly', fetch: 'readonly', URL: 'readonly', Image: 'readonly', FormData: 'readonly', XMLHttpRequest: 'readonly', setTimeout: 'readonly', clearTimeout: 'readonly', Intl: 'readonly', console: 'readonly', navigator: 'readonly', Blob: 'readonly', File: 'readonly', Date: 'readonly', process: 'readonly', Promise: 'readonly', structuredClone: 'readonly', requestAnimationFrame: 'readonly', cancelAnimationFrame: 'readonly', ResizeObserver: 'readonly', AbortController: 'readonly', Response: 'readonly', Headers: 'readonly', URLSearchParams: 'readonly', crypto: 'readonly', HTMLElement: 'readonly', sessionStorage: 'readonly' } },
    plugins: { 'react-hooks': reactHooks, 'jsx-a11y': jsxA11y,
      local: { rules: { 'no-physical-direction': { create: (ctx) => ({
        Literal(node) { if (typeof node.value === 'string' && physical.test(node.value)) ctx.report({ node, message: 'Use logical utilities (ms-/me-/ps-/pe-/start-/end-/text-start) instead of physical ones.' }) },
        TemplateElement(node) { if (physical.test(node.value.raw)) ctx.report({ node, message: 'Use logical utilities instead of physical ones.' }) },
      }) } } } },
    rules: { ...reactHooks.configs.recommended.rules, ...jsxA11y.flatConfigs.recommended.rules, 'local/no-physical-direction': 'warn' },
  },
]
