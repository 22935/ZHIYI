// Most component and workflow tests exercise an already-started desktop/web
// shell. Seed the same local owner marker that the launcher/profile bootstrap
// writes; individual identity and security tests clear it explicitly when
// they need to cover the unavailable-identity branch.
if (!localStorage.getItem('userId')) localStorage.setItem('userId', 'test-local-owner')
