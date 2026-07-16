import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.godtear.echo',
  appName: 'ECHO',
  webDir: 'dist',
  server: {
    // Default "https" makes the WebView load the app shell over
    // https://localhost, which then blocks its own fetches to the plain-HTTP
    // Tailscale backend as mixed content (independent of usesCleartextTraffic,
    // which only governs native networking, not the WebView's own policy).
    androidScheme: 'http'
  }
};

export default config;
