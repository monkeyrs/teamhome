const MESSAGES = require("../i18n/messages");
const MESSAGE_OVERRIDES = require("../i18n/messages-overrides");

const DEFAULT_LOCALE = "zh-CN";
const SUPPORTED_LOCALES = ["zh-CN", "en-US", "ja-JP"];

function normalizeLocale(locale) {
  if (!locale) return DEFAULT_LOCALE;
  if (SUPPORTED_LOCALES.includes(locale)) return locale;
  const lowered = String(locale).toLowerCase();
  if (lowered.startsWith("zh")) return "zh-CN";
  if (lowered.startsWith("en")) return "en-US";
  if (lowered.startsWith("ja")) return "ja-JP";
  return DEFAULT_LOCALE;
}

function getMessages(locale) {
  const normalized = normalizeLocale(locale);
  const base = MESSAGES[normalized] || MESSAGES[DEFAULT_LOCALE];
  const overrides = MESSAGE_OVERRIDES[normalized] || MESSAGE_OVERRIDES[DEFAULT_LOCALE] || {};
  return mergeMessages(base, overrides);
}

function mergeMessages(base, overrides) {
  if (!overrides || typeof overrides !== "object") {
    return base;
  }
  if (!base || typeof base !== "object") {
    return overrides;
  }
  const merged = Object.assign({}, base);
  Object.keys(overrides).forEach((key) => {
    const baseValue = base[key];
    const overrideValue = overrides[key];
    if (
      baseValue &&
      overrideValue &&
      typeof baseValue === "object" &&
      typeof overrideValue === "object" &&
      !Array.isArray(baseValue) &&
      !Array.isArray(overrideValue)
    ) {
      merged[key] = mergeMessages(baseValue, overrideValue);
      return;
    }
    merged[key] = overrideValue;
  });
  return merged;
}

function getLocale() {
  const app = typeof getApp === "function" ? getApp() : null;
  return normalizeLocale((app && app.globalData && app.globalData.locale) || wx.getStorageSync("locale") || DEFAULT_LOCALE);
}

function applyTabBarLocale(locale) {
  const messages = getMessages(locale);
  [
    messages.app.tabBar.assistant,
    messages.app.tabBar.schedule,
    messages.app.tabBar.finance,
    messages.app.tabBar.analysis
  ].forEach((text, index) => {
    try {
      wx.setTabBarItem({ index, text });
    } catch (err) {
      // Ignore if tab bar is not ready yet.
    }
  });
}

function setLocale(locale) {
  const normalized = normalizeLocale(locale);
  const app = typeof getApp === "function" ? getApp() : null;
  if (app && app.globalData) {
    app.globalData.locale = normalized;
  }
  wx.setStorageSync("locale", normalized);
  applyTabBarLocale(normalized);
  return normalized;
}

function getLanguageOptions(locale) {
  const messages = getMessages(locale);
  return SUPPORTED_LOCALES.map((code) => ({
    code,
    label: messages.app.languageOptions[code]
  }));
}

function applyPageLocale(page, pageKey) {
  const locale = getLocale();
  const messages = getMessages(locale);
  if (page && typeof page.setData === "function") {
    page.setData({
      locale,
      i18n: {
        app: messages.app,
        common: messages.common,
        page: messages[pageKey],
        chart: messages.chart
      },
      languageOptions: getLanguageOptions(locale)
    });
  }
  const title = messages.app.nav[pageKey];
  if (title) {
    wx.setNavigationBarTitle({ title });
  }
  applyTabBarLocale(locale);
}

module.exports = {
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
  getLocale,
  getMessages,
  setLocale,
  applyTabBarLocale,
  applyPageLocale,
  getLanguageOptions,
  normalizeLocale
};
