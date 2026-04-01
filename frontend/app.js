const { DEFAULT_LOCALE, applyTabBarLocale, normalizeLocale } = require("./utils/i18n");
const defaultConfig = require("./config/default");

let localConfig = {};
try {
  localConfig = require("./config/local");
} catch (err) {
  localConfig = {};
}

const runtimeConfig = Object.assign({}, defaultConfig, localConfig);

App({
  globalData: {
    apiBaseUrl: runtimeConfig.apiBaseUrl,
    token: "",
    currentTeamId: "",
    teams: [],
    user: null,
    locale: DEFAULT_LOCALE,
    dataSync: {
      financeByTeam: {},
      scheduleByTeam: {}
    }
  },
  onLaunch() {
    const token = wx.getStorageSync("token") || "";
    const user = wx.getStorageSync("user") || null;
    const locale = normalizeLocale((user && user.language) || wx.getStorageSync("locale") || DEFAULT_LOCALE);
    this.globalData.token = token;
    this.globalData.user = user;
    this.globalData.locale = locale;
    if (user && user.id) {
      this.globalData.currentTeamId = wx.getStorageSync(`currentTeamId:${user.id}`) || "";
    }
    applyTabBarLocale(locale);
  }
});
