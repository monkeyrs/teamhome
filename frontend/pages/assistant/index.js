const { setCurrentTeamId, setCurrentUser } = require("../../utils/request");
const { bootstrapSession } = require("../../utils/bootstrap");
const { applyPageLocale, setLocale } = require("../../utils/i18n");
const { markDataDirty } = require("../../utils/data-sync");
const assistantApi = require("./modules/api");
const { resolveTeamIndex, resolveCurrentTeam, syncTeamsToApp } = require("./modules/team-state");
const {
  createInitialData,
  translate,
  formatAnswerStatus: mapAnswerStatusText,
  quickReplyText,
  mapAssistantResponse
} = require("./modules/view-state");

const MUTATION_INTENTS = new Set(["create_finance", "create_schedule", "update_finance", "update_schedule", "delete_finance", "delete_schedule"]);

function createRequestToken() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function isMutationIntent(intent) {
  return MUTATION_INTENTS.has(String(intent || ""));
}

function syncDirtyScopesFromAssistant(teamId, response) {
  if (!teamId || !response || response.status !== "executed") return;

  const scopes = new Set();
  const results = response.data && response.data.results;
  if (Array.isArray(results)) {
    results.forEach((item) => {
      if (!item || item.status !== "executed") return;
      if (item.intent === "create_finance") scopes.add("finance");
      if (item.intent === "create_schedule") scopes.add("schedule");
    });
  }
  if (response.intent === "undo") {
    scopes.add("finance");
    scopes.add("schedule");
  }
  if (scopes.size === 0) return;
  markDataDirty({ teamId, scopes: Array.from(scopes) });
}

Page({
  data: createInitialData(),

  ensureRequestTracking() {
    if (!this._ignoredRequestTokens) {
      this._ignoredRequestTokens = new Set();
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
    return translate(this.data.i18n, path, params);
  },

  formatAnswerStatus(status) {
    return mapAnswerStatusText(status, {
      t: (path) => this.t(path),
      common: this.data.i18n.common
    });
  },

  getQuickReplyMessage(token) {
    return quickReplyText(token, {
      t: (path) => this.t(path),
      common: this.data.i18n.common
    });
  },

  async initPage() {
    this.setData({ loading: true });
    try {
      const { teamId, teams } = await bootstrapSession();
      const teamIndex = resolveTeamIndex(teams, teamId);
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
    return resolveCurrentTeam(this.data.teams, this.data.teamIndex);
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
      const user = await assistantApi.updateLanguage(locale);
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
    this.setData({
      teamIndex: index,
      teamPanelOpen: false,
      answer: "",
      answerDataText: "",
      answerStatus: "",
      answerStatusLabel: "",
      answerCanUndo: false,
      assistantConversationSessionId: "",
      assistantMutationSessionId: "",
      assistantReturnedSessionId: "",
      assistantMissingSlots: [],
      firstMissingSlot: ""
    });
    setCurrentTeamId(selected.id);
  },

  onTeamNameInput(event) {
    this.setData({ teamName: event.detail.value });
  },

  onQuestionInput(event) {
    this.setData({ question: event.detail.value });
  },

  async refreshTeams() {
    const teams = await assistantApi.listTeams();
    const teamIndex = syncTeamsToApp(teams);
    this.setData({
      teams,
      teamIndex: teamIndex < 0 ? 0 : teamIndex
    });
  },

  async createOrJoinTeam() {
    const name = (this.data.teamName || "").trim();
    if (!name) {
      wx.showToast({ title: this.t("page.teamNameRequired"), icon: "none" });
      return;
    }
    try {
      const team = await assistantApi.createTeam(name);
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
          await assistantApi.leaveTeam(teamId);
          await this.refreshTeams();
          this.setData({ teamPanelOpen: this.data.teams.length === 0 });
          wx.showToast({ title: this.t("page.leaveTeamSuccess"), icon: "success" });
        } catch (err) {
          wx.showToast({ title: this.t("page.leaveTeamFailed"), icon: "none" });
        }
      }
    });
  },

  stopCurrentRequest() {
    this.ensureRequestTracking();
    if (!this._activeRequestToken) return;
    this._ignoredRequestTokens.add(this._activeRequestToken);
    this.setData({
      assistantConversationSessionId: "",
      assistantMutationSessionId: "",
      assistantReturnedSessionId: ""
    });
  },

  async askAssistant() {
    if (this.data.loading) {
      this.stopCurrentRequest();
      return;
    }

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

    this.ensureRequestTracking();
    const continueMutation = !!this.data.assistantMutationSessionId && this.data.answerStatus === "collecting";
    const sessionId = continueMutation ? this.data.assistantMutationSessionId : (this.data.assistantConversationSessionId || null);

    const requestToken = createRequestToken();
    this._activeRequestToken = requestToken;
    this.setData({ loading: true });

    try {
      const data = await assistantApi.executeAssistant({
        teamId: team.id,
        message: question,
        sessionId
      });
      if (this._ignoredRequestTokens.has(requestToken)) {
        return;
      }

      syncDirtyScopesFromAssistant(team.id, data);
      const mapped = mapAssistantResponse(data, {
        clearQuestion: true,
        formatStatus: (status) => this.formatAnswerStatus(status)
      });
      const responseIntent = data && data.intent;
      const responseSessionId = (data && data.session_id) || "";
      const responseMode = data && data.data && data.data.session_mode;
      const responseIsMutation = responseMode === "mutation" || (!responseMode && isMutationIntent(responseIntent));
      if (responseIsMutation) {
        mapped.assistantConversationSessionId = "";
        mapped.assistantMutationSessionId = data && data.status === "collecting" ? responseSessionId : "";
      } else {
        mapped.assistantMutationSessionId = "";
        mapped.assistantConversationSessionId = responseSessionId;
      }
      this.setData(mapped);
    } catch (err) {
      if (this._ignoredRequestTokens.has(requestToken)) {
        return;
      }
      wx.showToast({ title: this.t("common.sendFailed"), icon: "none" });
    } finally {
      this._ignoredRequestTokens.delete(requestToken);
      if (this._activeRequestToken === requestToken) {
        this._activeRequestToken = "";
      }
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
      const data = await assistantApi.undoAssistant(team.id);
      syncDirtyScopesFromAssistant(team.id, data);
      const mapped = mapAssistantResponse(data, {
        clearQuestion: false,
        formatStatus: (status) => this.formatAnswerStatus(status)
      });
      mapped.assistantMutationSessionId = "";
      mapped.assistantConversationSessionId = "";
      this.setData(mapped);
    } catch (err) {
      wx.showToast({ title: this.t("common.sendFailed"), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
