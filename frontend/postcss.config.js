import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'

export default {
  plugins: [
    tailwindcss(),
    autoprefixer(),
    {
      postcssPlugin: 'roombeacon-viewport-fallback',
      Declaration(declaration) {
        // WebView 106 predates dynamic viewport units. Keep the modern override.
        if (/dvh\b/.test(declaration.value)) {
          declaration.cloneBefore({ value: declaration.value.replace(/dvh\b/g, 'vh') })
        }
      },
    },
  ],
}
