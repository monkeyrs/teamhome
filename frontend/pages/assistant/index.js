const { request, setCurrentTeamId, setCurrentUser } = require("../../utils/request");
const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");
const { applyPageLocale, setLocale } = require("../../utils/i18n");

Page({
  data: {
    teams: [],
    teamIndex: 0,
    teamName: "",
    teamPanelOpen: false,
    question: "",
    loading: false,
    answer: "",
    answerDataText: "",
    answerStatus: "",
    answerStatusLabel: "",
    answerCanUndo: false,
    assistantSessionId: "",
    assistantMissingSlots: [],
    firstMissingSlot: "",
    locale: "zh-CN",
    localeMenuOpen: false,
    languageOptions: [],
    i18n: {
      app: {},
      common: {},
      page: {},
      chart: {}
    }
  },

  async onShow() {
    this.applyLocale();
    await this.initPage();
  },

  applyLocale() {
    applyPageLocale(this, "assistant");
    this.setData({
      answerStatusLabel: this.formatAnswerStatus(this.data.answerStatus)
    });
  },

  t(path, params = {}) {
    const parts = path.split(".");
    let current = this.data.i18n;
    parts.forEach((part) => {
      current = current && current[part];
    });
    let text = typeof current === "string" ? current : path;
    Object.keys(params).forEach((key) => {
      text = text.replace(`{${key}}`, params[key]);
    });
    return text;
  },

  formatAnswerStatus(status) {
    const mapping = {
      awaiting_confirmation: this.data.i18n.common.confirm || status,
      collecting: this.t("page.collecting"),
      blocked: this.t("page.blocked"),
      collecting_conflict_update: this.t("page.conflictUpdate"),
      cancelled: this.data.i18n.common.cancel || status,
      executed: ""
    };
    return mapping[status] || status || "";
  },

  getQuickReplyMessage(token) {
    const mapping = {
      confirm: this.data.i18n.common.confirm,
      cancel: this.data.i18n.common.cancel,
      expense: this.t("page.expense"),
      income: this.t("page.income"),
      food: this.t("page.quickFood"),
      transport: this.t("page.quickTransport"),
      shopping: this.t("page.quickShopping"),
      reschedule: this.t("page.reschedule"),
      force_create: this.t("page.createAnyway")
    };
    return mapping[token] || "";
  },

  async initPage() {
    this.setData({ loading: true });
    try {
      const { teamId, teams } = await bootstrapSession();
      const teamIndex = Math.max(0, teams.findIndex((item) => item.id === teamId));
      this.setData({
        teams,
        teamIndex: teamIndex < 0 ? 0 : teamIndex,
        teamPanelOpen: teams.length === 0
      });
    } catch (err) {
      wx.showToast({ title: this.t("common.initFailed"), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  currentTeam() {
    const { teamId } = getCurrentTeamState();
    if (teamId) {
      const matched = (this.data.teams || []).find((item) => item.id === teamId);
      if (matched) {
        return matched;
      }
    }
    return this.data.teams[this.data.teamIndex] || null;
  },

  toggleTeamPanel() {
    this.setData({ teamPanelOpen: !this.data.teamPanelOpen });
  },

  toggleLocaleMenu() {
    this.setData({ localeMenuOpen: !this.data.localeMenuOpen });
  },

  async selectLanguage(event) {
    const locale = event.currentTarget.dataset.locale;
    if (!locale || locale === this.data.locale) {
      this.setData({ localeMenuOpen: false });
      return;
    }
    try {
      const user = await request({
        path: "/auth/me",
        method: "PUT",
        data: { language: locale }
      });
      setCurrentUser(user);
      setLocale(locale);
      this.setData({ localeMenuOpen: false });
      this.applyLocale();
      await this.initPage();
      wx.showToast({ title: this.t("page.languageSaved"), icon: "success" });
    } catch (err) {
      wx.showToast({ title: this.t("common.saveFailed"), icon: "none" });
    }
  },

  onSelectTeam(event) {
    const index = Number(event.currentTarget.dataset.index);
    const selected = this.data.teams[index];
    if (!selected) return;
    this.setData({ teamIndex: index, teamPanelOpen: false });
    setCurrentTeamId(selected.id);
  },

  onTeamNameInput(event) {
    this.setData({ teamName: event.detail.value });
  },

  onQuestionInput(event) {
    this.setData({ question: event.detail.value });
  },

  async refreshTeams() {
    const teams = await request({ path: "/teams" });
    const currentTeamId = getApp().globalData.currentTeamId || "";
    const teamIndex = Math.max(0, teams.findIndex((item) => item.id === currentTeamId));
    this.setData({
      teams,
      teamIndex: teamIndex < 0 ? 0 : teamIndex
    });
    getApp().globalData.teams = teams;
    if (teams.length > 0) {
      setCurrentTeamId(teams[Math.max(0, teamIndex)].id);
    } else {
      setCurrentTeamId("");
    }
  },

  async createOrJoinTeam() {
    const name = (this.data.teamName || "").trim();
    if (!name) {
      wx.showToast({ title: this.t("page.teamNameRequired"), icon: "none" });
      return;
    }
    try {
      const team = await request({
        path: "/teams",
        method: "POST",
        data: { name }
      });
      await this.refreshTeams();
      const teamIndex = this.data.teams.findIndex((item) => item.id === team.id);
      this.setData({
        teamName: "",
        teamIndex: teamIndex < 0 ? this.data.teamIndex : teamIndex,
        teamPanelOpen: false
      });
      setCurrentTeamId(team.id);
      wx.showToast({ title: this.t("page.teamJoinSuccess"), icon: "success" });
    } catch (err) {
      wx.showToast({ title: this.t("page.teamJoinInvalid"), icon: "none" });
    }
  },

  confirmLeaveTeam(event) {
    const teamId = event.currentTarget.dataset.teamId;
    const teamName = event.currentTarget.dataset.teamName;
    wx.showModal({
      title: this.t("page.leaveTeamTitle"),
      content: this.t("page.leaveTeamContent", { teamName }),
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await request({
            path: `/teams/${teamId}/members/me`,
            method: "DELETE"
          });
          await this.refreshTeams();
          this.setData({ teamPanelOpen: this.data.teams.length === 0 });
          wx.showToast({ title: this.t("page.leaveTeamSuccess"), icon: "success" });
        } catch (err) {
          wx.showToast({ title: this.t("page.leaveTeamFailed"), icon: "none" });
        }
      }
    });
  },

  async askAssistant() {
    const team = this.currentTeam();
    const question = (this.data.question || "").trim();
    if (!team) {
      wx.showToast({ title: this.t("page.noTeamJoined"), icon: "none" });
      return;
    }
    if (!question) {
      wx.showToast({ title: this.t("page.noQuestion"), icon: "none" });
      return;
    }

    this.setData({ loading: true });
    try {
      const data = await request({
        path: "/assistant/execute",
        method: "POST",
        data: {
          team_id: team.id,
          message: question,
          session_id: this.data.assistantSessionId || null
        }
      });
      this.setData({
        question: "",
        answer: data.reply || "",
        answerStatus: data.status || "",
        answerStatusLabel: this.formatAnswerStatus(data.status || ""),
        answerCanUndo: !!(data.data && data.data.can_undo),
        assistantSessionId: data.session_id || "",
        assistantMissingSlots: data.missing_slots || [],
        firstMissingSlot: (data.missing_slots && data.missing_slots[0]) || "",
        answerDataText: ""
      });
    } catch (err) {
      wx.showToast({ title: this.t("common.sendFailed"), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  onQuickReply(event) {
    const token = event.currentTarget.dataset.token;
    const text = this.getQuickReplyMessage(token);
    if (!text) return;
    this.setData({ question: text });
    this.askAssistant();
  },

  async undoAssistantBatch() {
    const team = this.currentTeam();
    if (!team) {
      wx.showToast({ title: this.t("page.noTeamJoined"), icon: "none" });
      return;
    }
    this.setData({ loading: true });
    try {
      const data = await request({
        path: "/assistant/undo",
        method: "POST",
        data: { team_id: team.id }
      });
      this.setData({
        answer: data.reply || "",
        answerStatus: data.status || "",
        answerStatusLabel: this.formatAnswerStatus(data.status || ""),
        answerCanUndo: !!(data.data && data.data.can_undo),
        assistantSessionId: data.session_id || "",
        assistantMissingSlots: data.missing_slots || [],
        firstMissingSlot: (data.missing_slots && data.missing_slots[0]) || "",
        answerDataText: ""
      });
    } catch (err) {
      wx.showToast({ title: this.t("common.sendFailed"), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
