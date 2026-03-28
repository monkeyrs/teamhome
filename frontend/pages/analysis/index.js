const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");
const { applyPageLocale, translateMessage } = require("../../utils/i18n");
const { getDataVersion } = require("../../utils/data-sync");
const analysisApi = require("./modules/api");
const { buildAnalysis } = require("./modules/metrics");

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    hasTeam: true,
    teamReady: false,
    currentTeamId: "",
    financeSyncVersion: 0,
    scheduleSyncVersion: 0,
    summaryCards: [],
    categoryBars: [],
    weekdayBars: [],
    memberBars: [],
    recentExpenseBars: [],
    timeBuckets: [],
    locale: "zh-CN",
    i18n: {
      app: {},
      common: {},
      page: {},
      chart: {}
    }
  },

  async onShow() {
    this.applyLocale();
    const { teamId } = getCurrentTeamState();
    if (!this.data.teamReady || this.data.currentTeamId !== teamId) {
      await this.initPage();
      return;
    }
    const financeVersion = getDataVersion("finance", teamId);
    const scheduleVersion = getDataVersion("schedule", teamId);
    if (
      financeVersion > (this.data.financeSyncVersion || 0) ||
      scheduleVersion > (this.data.scheduleSyncVersion || 0)
    ) {
      this.setData({ loading: true });
      try {
        await this.loadAnalysis(teamId);
        this.setData({
          financeSyncVersion: financeVersion,
          scheduleSyncVersion: scheduleVersion
        });
      } catch (err) {
        wx.showToast({ title: this.t("common.loadFailed"), icon: "none" });
      } finally {
        this.setData({ loading: false });
      }
    }
  },

  applyLocale() {
    applyPageLocale(this, "analysis");
  },

  t(path, params = {}) {
    return translateMessage(this.data.i18n, path, params);
  },

  async initPage() {
    this.setData({ loading: true });
    try {
      const { teamId, teams } = await bootstrapSession();
      this.setData({
        teams,
        hasTeam: !!teamId,
        teamReady: true,
        currentTeamId: teamId,
        financeSyncVersion: 0,
        scheduleSyncVersion: 0
      });
      if (!teamId) {
        this.setEmptyAnalysis();
        return;
      }
      const teamIndex = Math.max(0, teams.findIndex((item) => item.id === teamId));
      this.setData({ teamIndex });
      await this.loadAnalysis(teamId);
      this.setData({
        financeSyncVersion: getDataVersion("finance", teamId),
        scheduleSyncVersion: getDataVersion("schedule", teamId)
      });
    } catch (err) {
      wx.showToast({ title: this.t("common.initFailed"), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  setEmptyAnalysis() {
    this.setData({
      summaryCards: [],
      categoryBars: [],
      weekdayBars: [],
      memberBars: [],
      recentExpenseBars: [],
      timeBuckets: []
    });
  },

  async loadAnalysis(teamId) {
    const [schedules, records] = await Promise.all([
      analysisApi.listSchedules(teamId),
      analysisApi.listFinance(teamId)
    ]);
    const next = buildAnalysis(records || [], schedules || [], (path) => this.t(path));
    this.setData(next);
  },

  goAssistantPage() {
    wx.switchTab({ url: "/pages/assistant/index" });
  },

  async downloadAllData() {
    try {
      wx.showLoading({ title: this.t("page.downloadPreparing"), mask: true });
      const res = await analysisApi.downloadAssistantData();
      const filePath = res && res.tempFilePath;
      if (!filePath) {
        throw new Error("Missing temp file path");
      }
      wx.hideLoading();
      wx.openDocument({
        filePath,
        showMenu: true,
        success: () => {
          wx.showToast({ title: this.t("page.downloadReady"), icon: "success" });
        },
        fail: () => {
          wx.showToast({ title: this.t("page.downloadOpenFailed"), icon: "none" });
        }
      });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: this.t("page.downloadFailed"), icon: "none" });
    }
  }
});
