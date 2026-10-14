// Run before the stylesheet so the initial paint uses the correct theme.
(() => {
  const key = 'sjtu-run-web:theme';
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const modes = ['system', 'light', 'dark'];
  let preference = 'system';
  try { const saved = localStorage.getItem(key); if (modes.includes(saved)) preference = saved; } catch {}
  function apply() {
    const theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference;
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#181818' : '#ffffff');
    const select = document.getElementById('theme-select');
    if (select) select.value = preference;
  }
  media.addEventListener('change', apply);
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) { preference = modes.includes(event.newValue) ? event.newValue : 'system'; apply(); }
  });
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('theme-select').addEventListener('change', event => {
      preference = event.target.value;
      try { localStorage.setItem(key, preference); } catch {}
      apply();
    });
    apply();
  });
  apply();
})();
