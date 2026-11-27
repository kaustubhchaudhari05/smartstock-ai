/** Follow the operating system's light/dark preference using Bootstrap 5.3 color modes. */
export function followSystemTheme(): void {
  const query = window.matchMedia('(prefers-color-scheme: dark)')
  const apply = () =>
    document.documentElement.setAttribute('data-bs-theme', query.matches ? 'dark' : 'light')
  apply()
  query.addEventListener('change', apply)
}
