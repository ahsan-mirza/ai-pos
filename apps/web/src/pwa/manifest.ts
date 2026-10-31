/** Identity shared by the Vite PWA plugin and the manifest tests. */
export const pwaManifest = {
  id: "/",
  name: "AxizPOS Business Pro",
  short_name: "Business Pro",
  description: "Manage your business operations with AxizPOS Business Pro.",
  start_url: "/",
  scope: "/",
  display: "standalone" as const,
  orientation: "any" as const,
  theme_color: "#f26a21",
  background_color: "#eaeaea",
  icons: [
    { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
    { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    { src: "/icons/icon-maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
    { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
  ],
  shortcuts: [
    {
      name: "Dashboard",
      short_name: "Home",
      url: "/",
      icons: [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
    },
  ],
};

export const PWA_ICONS = [
  "icon-192.png",
  "icon-512.png",
  "icon-maskable-192.png",
  "icon-maskable-512.png",
  "apple-touch-icon.png",
  "favicon-32.png",
];
