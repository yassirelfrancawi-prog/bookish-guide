// Fourni par telegram-web-app.js quand l'app tourne dans Telegram.
interface TelegramWebApp {
  initData: string;
  colorScheme?: "light" | "dark";
  ready: () => void;
  expand: () => void;
}
interface Window {
  Telegram?: { WebApp?: TelegramWebApp };
}
