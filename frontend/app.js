const { DEFAULT_LOCALE, applyTabBarLocale, normalizeLocale } = require("./utils/i18n");

App({
  globalData: {
    apiBaseUrl: "http://127.0.0.1:8000",
    //apiBaseUrl: "http://your-domain.example:8000",  //dont delete, production!
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
