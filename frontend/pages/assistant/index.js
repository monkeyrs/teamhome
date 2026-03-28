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

function buildProfileState(user) {
  const nickname = (user && user.nickname) || "";
  return {
    nicknamePromptOpen: !nickname,
    profileNickname: nickname,
    profileLocked: !!nickname
  };
}

function getTeamPasswordVisibilityMap(teams) {
  const visibilityMap = {};
  (teams || []).forEach((item) => {
    visibilityMap[item.id] = !!item.passwordVisible;
  });
  return visibilityMap;
}

function decorateTeams(teams, visibilityMap, t) {
  return (teams || []).map((item) => {
    const passwordVisible = !!visibilityMap[item.id];
    const hasPassword = !!item.join_password;
    return {
      ...item,
      passwordVisible,
      passwordButtonText: hasPassword
        ? (passwordVisible ? item.join_password : t("page.teamPasswordToggle"))
        : ""
    };
  });
}

function resetTeamPasswordVisibility(teams, t) {
  return decorateTeams(teams, {}, t);
}

function buildPasswordCells(password) {
  const normalized = String(password || "").slice(0, 4);
  return Array.from({ length: 4 }, (_, index) => normalized[index] || "");
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
    const visibilityMap = getTeamPasswordVisibilityMap(this.data.teams);
    this.setData({
      teams: decorateTeams(this.data.teams, visibilityMap, (path) => this.t(path)),
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
      const { teamId, teams, user } = await bootstrapSession();
      const teamIndex = resolveTeamIndex(teams, teamId);
      const visibilityMap = getTeamPasswordVisibilityMap(this.data.teams);
      this.setData({
        ...buildProfileState(user),
        canUseNicknameInput: wx.canIUse("input.type.nickname"),
        teams: decorateTeams(teams, visibilityMap, (path) => this.t(path)),
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
    const nextOpen = !this.data.teamPanelOpen;
    this.setData({
      teamPanelOpen: nextOpen,
      teams: resetTeamPasswordVisibility(this.data.teams, (path) => this.t(path))
    });
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
      teams: resetTeamPasswordVisibility(this.data.teams, (path) => this.t(path)),
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

  onProfileNicknameInput(event) {
    this.setData({ profileNickname: event.detail.value });
  },

  async submitProfile(event) {
    if (this.data.savingProfile || this.data.profileLocked) return;

    const formNickname = (((event || {}).detail || {}).value || {}).nickname;
    const nickname = String(formNickname != null ? formNickname : this.data.profileNickname || "").trim();
    if (!nickname) {
      wx.showToast({ title: this.t("page.profileNicknameRequired"), icon: "none" });
      return;
    }

    this.setData({ savingProfile: true });
    try {
      const user = await assistantApi.updateProfile({ nickname });
      setCurrentUser(user);
      this.setData(buildProfileState(user));
      wx.showToast({ title: this.t("page.profileSaved"), icon: "success" });
    } catch (err) {
      const detail = err && err.responseData && err.responseData.detail;
      wx.showToast({ title: detail === "NICKNAME_LOCKED" ? this.t("page.profileLockedError") : this.t("common.saveFailed"), icon: "none" });
    } finally {
      this.setData({ savingProfile: false });
    }
  },

  async refreshTeams() {
    const teams = await assistantApi.listTeams();
    const teamIndex = syncTeamsToApp(teams);
    const visibilityMap = getTeamPasswordVisibilityMap(this.data.teams);
    this.setData({
      teams: decorateTeams(teams, visibilityMap, (path) => this.t(path)),
      teamIndex: teamIndex < 0 ? 0 : teamIndex
    });
    return teams;
  },

  openTeamDialog(mode, name) {
    this.setData({
      teamDialogOpen: true,
      teamDialogMode: mode,
      teamDialogName: name,
      teamDialogPassword: "",
      teamDialogPasswordCells: buildPasswordCells(""),
      teamDialogSubmitting: false
    });
  },

  closeTeamDialog() {
    if (this.data.teamDialogSubmitting) return;
    this.setData({
      teamDialogOpen: false,
      teamDialogMode: "",
      teamDialogName: "",
      teamDialogPassword: "",
      teamDialogPasswordCells: buildPasswordCells(""),
      teamDialogSubmitting: false
    });
  },

  noop() {},

  focusTeamDialogPasswordInput() {
    this.setData({ teamDialogPasswordFocus: true });
  },

  onTeamDialogPasswordBlur() {
    this.setData({ teamDialogPasswordFocus: false });
  },

  onTeamDialogPasswordInput(event) {
    const value = String(event.detail.value || "").replace(/\D/g, "").slice(0, 4);
    this.setData({
      teamDialogPassword: value,
      teamDialogPasswordCells: buildPasswordCells(value)
    });
  },

  toggleTeamPassword(event) {
    const teamId = event.currentTarget.dataset.teamId;
    if (!teamId) return;
    const visibilityMap = getTeamPasswordVisibilityMap(this.data.teams);
    visibilityMap[teamId] = !visibilityMap[teamId];
    this.setData({
      teams: decorateTeams(this.data.teams, visibilityMap, (path) => this.t(path))
    });
  },

  async createOrJoinTeam() {
    const name = (this.data.teamName || "").trim();
    if (!name) {
      wx.showToast({ title: this.t("page.teamNameRequired"), icon: "none" });
      return;
    }

    this.setData({ teamActionLoading: true });
    try {
      const discovery = await assistantApi.discoverTeam(name);
      if (discovery.already_joined) {
        const teams = await this.refreshTeams();
        const joinedIndex = teams.findIndex((item) => item.name === name);
        if (joinedIndex >= 0) {
          this.setData({ teamIndex: joinedIndex, teamPanelOpen: false });
          setCurrentTeamId(teams[joinedIndex].id);
        }
        wx.showToast({ title: this.t("page.teamAlreadyJoined"), icon: "none" });
        return;
      }
      if (discovery.team_full) {
        wx.showToast({ title: this.t("page.teamMemberLimitReached"), icon: "none" });
        return;
      }
      if (discovery.exists && !discovery.requires_password) {
        const team = await assistantApi.createTeam({ name });
        const teams = await this.refreshTeams();
        const joinedIndex = teams.findIndex((item) => item.id === team.id);
        this.setData({
          teamName: "",
          teams: resetTeamPasswordVisibility(teams, (path) => this.t(path)),
          teamIndex: joinedIndex < 0 ? this.data.teamIndex : joinedIndex,
          teamPanelOpen: false
        });
        setCurrentTeamId(team.id);
        wx.showToast({ title: this.t("page.teamJoinSuccess"), icon: "success" });
        return;
      }
      this.openTeamDialog(discovery.exists ? "join" : "create", name);
    } catch (err) {
      wx.showToast({ title: this.t("page.teamJoinInvalid"), icon: "none" });
    } finally {
      this.setData({ teamActionLoading: false });
    }
  },

  async confirmTeamDialog() {
    const mode = this.data.teamDialogMode;
    const name = (this.data.teamDialogName || "").trim();
    const password = String(this.data.teamDialogPassword || "").trim();
    if (!name) return;

    if (mode === "join" && password.length !== 4) {
      wx.showToast({ title: this.t("page.teamPasswordRequired"), icon: "none" });
      return;
    }
    if (mode === "create" && password && password.length !== 4) {
      wx.showToast({ title: this.t("page.teamPasswordRequired"), icon: "none" });
      return;
    }

    this.setData({ teamDialogSubmitting: true });
    try {
      const team = await assistantApi.createTeam({
        name,
        password: password || undefined
      });
      const teams = await this.refreshTeams();
      const teamIndex = teams.findIndex((item) => item.id === team.id);
      this.setData({
        teamName: "",
        teams: resetTeamPasswordVisibility(teams, (path) => this.t(path)),
        teamIndex: teamIndex < 0 ? this.data.teamIndex : teamIndex,
        teamPanelOpen: false,
        teamDialogOpen: false,
        teamDialogMode: "",
        teamDialogName: "",
        teamDialogPassword: "",
        teamDialogPasswordCells: buildPasswordCells(""),
        teamDialogPasswordFocus: false,
        teamDialogSubmitting: false
      });
      setCurrentTeamId(team.id);
      wx.showToast({ title: mode === "create" ? this.t("page.teamCreateSuccess") : this.t("page.teamJoinSuccess"), icon: "success" });
    } catch (err) {
      const detail = err && err.responseData && err.responseData.detail;
      let title = this.t("page.teamJoinInvalid");
      if (detail === "TEAM_PASSWORD_REQUIRED") title = this.t("page.teamPasswordRequired");
      if (detail === "TEAM_PASSWORD_INVALID") title = this.t("page.teamPasswordInvalid");
      if (detail === "TEAM_MEMBER_LIMIT_REACHED") title = this.t("page.teamMemberLimitReached");
      wx.showToast({ title, icon: "none" });
      this.setData({ teamDialogSubmitting: false });
      return;
    } finally {
      if (this.data.teamDialogSubmitting) {
        this.setData({ teamDialogSubmitting: false });
      }
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
