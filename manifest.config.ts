import { defineManifest } from "@crxjs/vite-plugin";

export default defineManifest({
  manifest_version: 3,
  name: "note.com フォロー",
  description:
    "note.com のログイン Cookie を使い、フォロワーへのフォロー返しとお礼メッセージ送信を行います。パスワードは保存しません。",
  version: "0.3.2",
  action: {
    default_title: "note.com フォロー",
    default_popup: "src/popup/index.html",
    default_icon: {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png",
    },
  },
  options_ui: {
    page: "src/options/index.html",
    open_in_tab: true,
  },
  background: {
    service_worker: "src/background.ts",
    type: "module",
  },
  content_scripts: [
    {
      matches: ["https://note.com/*"],
      js: ["src/content/fill-thanks.ts"],
      run_at: "document_idle",
    },
  ],
  icons: {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png",
  },
  permissions: ["storage", "alarms", "cookies", "tabs", "clipboardWrite", "notifications"],
  host_permissions: ["https://note.com/*"],
});
