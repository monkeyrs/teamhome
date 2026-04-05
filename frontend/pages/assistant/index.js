const { setCurrentTeamId, setCurrentUser } = require("../../utils/request");
const { bootstrapSession, refreshUserInfo } = require("../../utils/bootstrap");
const { applyPageLocale, getLocale, getMessages, setLocale } = require("../../utils/i18n");
const { markDataDirty } = require("../../utils/data-sync");
const { triggerFeedback } = require("../../utils/feedback");
const assistantApi = require("./modules/api");
const { resolveTeamIndex, resolveCurrentTeam, syncTeamsToApp } = require("./modules/team-state");
const {
  createInitialData,
  createEmptyAssistantGraphState,
  normalizeGraphState,
  translate,
  formatAnswerStatus: mapAnswerStatusText,
  buildAssistantGraphNodes,
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

function shouldContinueAssistantSession(status) {
  return [
    "collecting",
    "awaiting_confirmation",
    "blocked",
    "collecting_conflict_update"
  ].includes(String(status || ""));
}

function buildProfileState(user) {
  const nickname = (user && user.nickname) || "";
  return {
    nicknamePromptOpen: !nickname,
    profileNickname: nickname,
    profileLocked: !!nickname,
    nicknameCelebrateActive: false
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
    const isDemo = !!item.is_demo;
    return {
      ...item,
      isDemo,
      isReadonly: !!item.is_readonly,
      passwordVisible,
      metaText: isDemo
        ? t("page.teamDemoMeta")
        : `${item.member_count}/30`,
      passwordButtonText: hasPassword
        ? (passwordVisible ? item.join_password : t("page.teamPasswordToggle"))
        : ""
    };
  });
}

function resetTeamPasswordVisibility(teams, t) {
  return decorateTeams(teams, {}, t);
}

function buildDemoEntryOptions(t) {
  return [
    {
      key: "badz",
      teamName: "Badz乐队",
      displayName: t("page.demoTeamBadz")
    },
    {
      key: "teamhome",
      teamName: "teamhome开发",
      displayName: t("page.demoTeamLog")
    }
  ];
}

function filterJoinedDemoEntryOptions(options, teams) {
  const joinedNames = new Set((teams || []).map((item) => String((item && item.name) || "").trim()).filter(Boolean));
  return (options || []).filter((item) => !joinedNames.has(String(item.teamName || "").trim()));
}

function buildVisibleDemoEntryOptions(teams, t) {
  return filterJoinedDemoEntryOptions(buildDemoEntryOptions(t), teams);
}

function isKnownDemoTeamName(name) {
  return name === "Badz乐队" || name === "teamhome开发";
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

  getProcessingText() {
    const locale = this.data.locale || getLocale();
    const messages = getMessages(locale);
    return (((messages || {}).assistant || {}).processingText) || "处理中";
  },

  getProcessingTickDelay() {
    return 1000 + Math.floor(Math.random() * 2001);
  },

  scheduleProcessingTick() {
    this._processingTimer = setTimeout(() => {
      const nextDots = ((this.data.processingDots || 0) % 6) + 1;
      this.setData({
        processingDots: nextDots,
        answer: `${this.getProcessingText()}${".".repeat(nextDots)}`
      });
      triggerFeedback(this, { hapticKey: "assistant-processing-dot" });
      this.scheduleProcessingTick();
    }, this.getProcessingTickDelay());
  },

  createLoadingGraphState(sessionId) {
    const graphState = createEmptyAssistantGraphState();
    graphState.available = true;
    graphState.threadId = sessionId || "";
    graphState.threadStatus = "busy";
    graphState.highlightedStages = ["prepare"];
    graphState.activeStage = "prepare";
    return graphState;
  },

  ensureVisibleGraphState(graphState, sessionId) {
    const normalized = normalizeGraphState(graphState);
    if (!normalized.highlightedStages.length && (normalized.available || normalized.threadId || sessionId || this.data.loading)) {
      normalized.highlightedStages = ["prepare"];
      normalized.activeStage = "prepare";
    }
    if (!normalized.activeStage && normalized.highlightedStages.length) {
      normalized.activeStage = normalized.highlightedStages[normalized.highlightedStages.length - 1];
    }
    return normalized;
  },

  startProcessingIndicator(sessionId) {
    const loadingGraphState = this.createLoadingGraphState(sessionId);
    this.stopProcessingIndicator();
    this.setData({
      answer: this.getProcessingText(),
      processingDots: 0,
      answerDataText: "",
      answerStatus: "",
      answerStatusLabel: "",
      answerCanUndo: false,
      assistantReturnedSessionId: "",
      assistantMissingSlots: [],
      firstMissingSlot: "",
      assistantGraphState: loadingGraphState,
      assistantGraphNodes: buildAssistantGraphNodes(loadingGraphState, this.data.graphI18n || {})
    });

    this.scheduleProcessingTick();
  },

  stopProcessingIndicator() {
    if (this._processingTimer) {
      clearTimeout(this._processingTimer);
      this._processingTimer = null;
    }
  },

  stopGraphPulse() {
    if (this._graphPulseTimer) {
      clearTimeout(this._graphPulseTimer);
      this._graphPulseTimer = null;
    }
    if (this.data.assistantGraphPulseActive) {
      this.setData({ assistantGraphPulseActive: false });
    }
  },

  triggerGraphPulse() {
    this.stopGraphPulse();
    this.setData({ assistantGraphPulseActive: true });
    this._graphPulseTimer = setTimeout(() => {
      this._graphPulseTimer = null;
      this.setData({ assistantGraphPulseActive: false });
    }, 950);
  },

  stopGraphStatePolling() {
    if (this._graphStatePollingTimer) {
      clearTimeout(this._graphStatePollingTimer);
      this._graphStatePollingTimer = null;
    }
  },

  async pollGraphState(teamId, sessionId, requestToken) {
    if (this._activeRequestToken !== requestToken || this._ignoredRequestTokens.has(requestToken)) {
      return;
    }
    try {
      const payload = await assistantApi.getAssistantGraphState({ teamId, sessionId });
      if (this._activeRequestToken !== requestToken || this._ignoredRequestTokens.has(requestToken)) {
        return;
      }
      const graphState = this.ensureVisibleGraphState(payload && payload.graph_state, sessionId);
      this.setData({
        assistantGraphState: graphState,
        assistantGraphNodes: buildAssistantGraphNodes(graphState, this.data.graphI18n || {})
      });
    } catch (err) {
      // Ignore transient polling errors and keep the last rendered graph state.
    } finally {
      if (this.data.loading && this._activeRequestToken === requestToken && !this._ignoredRequestTokens.has(requestToken)) {
        this._graphStatePollingTimer = setTimeout(() => {
          this.pollGraphState(teamId, sessionId, requestToken);
        }, 500);
      }
    }
  },

  scheduleGraphStatePolling(teamId, sessionId, requestToken) {
    this.stopGraphStatePolling();
    if (!teamId || !sessionId) {
      return;
    }
    this.pollGraphState(teamId, sessionId, requestToken);
  },

  ensureRequestTracking() {
    if (!this._ignoredRequestTokens) {
      this._ignoredRequestTokens = new Set();
    }
  },

  async onShow() {
    this.applyLocale();
    await this.initPage();
  },

  onHide() {
    this.stopProcessingIndicator();
    this.stopGraphStatePolling();
    this.stopGraphPulse();
    this.stopNicknameCelebrate();
  },

  onUnload() {
    this.stopProcessingIndicator();
    this.stopGraphStatePolling();
    this.stopGraphPulse();
    this.stopNicknameCelebrate();
  },

  applyLocale() {
    const locale = getLocale();
    const messages = getMessages(locale);
    const localizedNicknameSetupTitle = (
      (((messages || {}).assistant || {}).nicknameSetupTitleFun)
      || (
        locale === "en-US"
          ? "Hey! What should I call you? 😊"
          : locale === "ja-JP"
            ? "ねえ、なんて呼べばいい？😊"
            : "嘿！请叫我什么？😊"
      )
    );
    const localizedGraphSpeedBoosted = (
      (((messages || {}).assistant || {}).graphSpeedBoosted)
      || (
        locale === "en-US"
          ? "Speed mode activated"
          : locale === "ja-JP"
            ? "スピードモードを開始しました"
            : "加速模式已启动"
      )
    );
    applyPageLocale(this, "assistant");
    const visibilityMap = getTeamPasswordVisibilityMap(this.data.teams);
    this.setData({
      nicknameSetupTitleFunText: localizedNicknameSetupTitle,
      graphI18n: messages.analysis || {},
      teams: decorateTeams(this.data.teams, visibilityMap, (path) => this.t(path)),
      demoEntryOptions: buildVisibleDemoEntryOptions(this.data.teams, (path) => this.t(path)),
      answerStatusLabel: this.formatAnswerStatus(this.data.answerStatus),
      assistantGraphNodes: buildAssistantGraphNodes(this.data.assistantGraphState, messages.analysis || {}),
      answer: this.data.loading
        ? `${this.getProcessingText()}${".".repeat(this.data.processingDots || 0)}`
        : this.data.answer
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
      const freshUser = await refreshUserInfo();
      const { teamId, teams, user, realTeams, demoTeams, capabilities } = await bootstrapSession();
      const profileUser = freshUser || user || (((getApp() || {}).globalData || {}).user) || null;
      const teamIndex = resolveTeamIndex(teams, teamId);
      const visibilityMap = getTeamPasswordVisibilityMap(this.data.teams);
      this.setData({
        ...buildProfileState(profileUser),
        canUseNicknameInput: wx.canIUse("input.type.nickname"),
        teams: decorateTeams(teams, visibilityMap, (path) => this.t(path)),
        realTeams: realTeams || [],
        demoTeams: demoTeams || [],
        demoEntryOptions: buildVisibleDemoEntryOptions(teams, (path) => this.t(path)),
        teamIndex: teamIndex < 0 ? 0 : teamIndex,
        teamPanelOpen: !!(capabilities && capabilities.shouldPromptTeamEntry),
        teamInputFocused: false
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

  showReadonlyTip() {
    wx.showToast({ title: this.t("page.readonlyTip"), icon: "none" });
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
      processingDots: 0,
      answerDataText: "",
      answerStatus: "",
      answerStatusLabel: "",
      answerCanUndo: false,
      assistantConversationSessionId: "",
      assistantMutationSessionId: "",
      assistantReturnedSessionId: "",
      assistantMissingSlots: [],
      firstMissingSlot: "",
      assistantGraphState: createEmptyAssistantGraphState(),
      assistantGraphNodes: buildAssistantGraphNodes(createEmptyAssistantGraphState(), this.data.graphI18n || {})
    });
    setCurrentTeamId(selected.id);
  },

  onTeamNameInput(event) {
    this.setData({ teamName: event.detail.value, teamInputFocused: true });
  },

  onTeamNameFocus() {
    this.setData({ teamInputFocused: true });
  },

  onTeamNameBlur() {
    setTimeout(() => {
      this.setData({ teamInputFocused: false });
    }, 120);
  },

  async openDemoTeamFromEntry(event) {
    const teamName = String(event.currentTarget.dataset.teamName || "").trim();
    if (!teamName || this.data.teamActionLoading) return;
    this.setData({
      teamName,
      teamInputFocused: false
    });
    await this.openDemoTeam(teamName);
  },

  async openDemoTeam(teamName) {
    const name = String(teamName || "").trim();
    if (!name) return;

    this.setData({ teamActionLoading: true });
    try {
      const discovery = await assistantApi.discoverTeam(name);
      if (!discovery.exists || !discovery.is_demo) {
        wx.showToast({ title: this.t("page.demoTeamUnavailable"), icon: "none" });
        return;
      }

      const team = await assistantApi.createTeam({ name });
      const teams = await this.refreshTeams();
      const joinedIndex = teams.findIndex((item) => item.id === team.id);
      this.setData({
        teamName: "",
        teams: resetTeamPasswordVisibility(teams, (path) => this.t(path)),
        teamIndex: joinedIndex < 0 ? this.data.teamIndex : joinedIndex,
        teamPanelOpen: false,
        teamInputFocused: false
      });
      setCurrentTeamId(team.id);
    } catch (err) {
      wx.showToast({ title: this.t("page.demoTeamUnavailable"), icon: "none" });
    } finally {
      this.setData({ teamActionLoading: false });
    }
  },

  onQuestionInput(event) {
    this.setData({ question: event.detail.value });
  },

  onProfileNicknameInput(event) {
    this.setData({ profileNickname: event.detail.value });
  },

  stopNicknameCelebrate() {
    if (this._nicknameCelebrateTimer) {
      clearTimeout(this._nicknameCelebrateTimer);
      this._nicknameCelebrateTimer = null;
    }
    if (this.data.nicknameCelebrateActive) {
      this.setData({ nicknameCelebrateActive: false });
    }
  },

  triggerNicknameCelebrate() {
    this.stopNicknameCelebrate();
    this.setData({ nicknameCelebrateActive: true });
    this._nicknameCelebrateTimer = setTimeout(() => {
      this._nicknameCelebrateTimer = null;
      this.setData({ nicknameCelebrateActive: false });
    }, 1500);
  },

  onGraphNodeLongPress(event) {
    const index = Number(event.currentTarget.dataset.index);
    const node = this.data.assistantGraphNodes[index];
    if (!node) return;
    wx.showModal({
      title: node.title,
      content: node.desc || "",
      showCancel: false,
      confirmText: this.t("common.confirm")
    });
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
      this.triggerNicknameCelebrate();
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
    const realTeams = (teams || []).filter((item) => !item.is_demo);
    const demoTeams = (teams || []).filter((item) => !!item.is_demo);
    this.setData({
      teams: decorateTeams(teams, visibilityMap, (path) => this.t(path)),
      realTeams,
      demoTeams,
      demoEntryOptions: buildVisibleDemoEntryOptions(teams, (path) => this.t(path)),
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

  async createOrJoinTeam(prefilledName) {
    const rawName = typeof prefilledName === "string" ? prefilledName : (this.data.teamName || "");
    const name = String(rawName).trim();
    if (!name) {
      wx.showToast({ title: this.t("page.teamNameRequired"), icon: "none" });
      return;
    }

    if (isKnownDemoTeamName(name)) {
      await this.openDemoTeam(name);
      return;
    }

    this.setData({ teamActionLoading: true });
    try {
      const discovery = await assistantApi.discoverTeam(name);
      if (discovery.already_joined) {
        const teams = await this.refreshTeams();
        const joinedIndex = teams.findIndex((item) => item.name === name);
        if (joinedIndex >= 0) {
          this.setData({ teamIndex: joinedIndex, teamPanelOpen: false, teamInputFocused: false });
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
          teamPanelOpen: false,
          teamInputFocused: false
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
        teamInputFocused: false,
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
    const isDemo = event.currentTarget.dataset.isDemo === true || event.currentTarget.dataset.isDemo === "true";
    wx.showModal({
      title: this.t(isDemo ? "page.leaveDemoTitle" : "page.leaveTeamTitle"),
      content: this.t(isDemo ? "page.leaveDemoContent" : "page.leaveTeamContent", { teamName }),
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
    this.stopProcessingIndicator();
    this.stopGraphStatePolling();
    this.stopGraphPulse();
    this.setData({
      loading: false,
      assistantConversationSessionId: "",
      assistantMutationSessionId: "",
      assistantReturnedSessionId: "",
      processingDots: 0,
      assistantGraphState: createEmptyAssistantGraphState(),
      assistantGraphNodes: buildAssistantGraphNodes(createEmptyAssistantGraphState(), this.data.graphI18n || {})
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
    const isIdleGraphState = !this.data.loading
      && !this.data.answer
      && !((this.data.assistantGraphState && this.data.assistantGraphState.highlightedStages) || []).length;
    const continueMutation = !!this.data.assistantMutationSessionId && shouldContinueAssistantSession(this.data.answerStatus);
    const continueConversation = !!this.data.assistantConversationSessionId && shouldContinueAssistantSession(this.data.answerStatus);
    const sessionId = continueMutation
      ? this.data.assistantMutationSessionId
      : (continueConversation ? this.data.assistantConversationSessionId : createRequestToken());

    const requestToken = createRequestToken();
    this._activeRequestToken = requestToken;
    if (isIdleGraphState) {
      this.triggerGraphPulse();
    }
    this.setData({ loading: true });
    this.startProcessingIndicator(sessionId);
    this.scheduleGraphStatePolling(team.id, sessionId, requestToken);

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
      const responseSessionId = (data && data.session_id) || "";
      const mapped = mapAssistantResponse(data, {
        clearQuestion: true,
        formatStatus: (status) => this.formatAnswerStatus(status)
      });
      mapped.assistantGraphState = this.ensureVisibleGraphState(mapped.assistantGraphState, responseSessionId);
      mapped.processingDots = 0;
      mapped.assistantGraphNodes = buildAssistantGraphNodes(mapped.assistantGraphState, this.data.graphI18n || {});
      const responseIntent = data && data.intent;
      const responseMode = data && data.data && data.data.session_mode;
      const responseIsMutation = responseMode === "mutation" || (!responseMode && isMutationIntent(responseIntent));
      if (responseIsMutation) {
        mapped.assistantConversationSessionId = "";
        mapped.assistantMutationSessionId = shouldContinueAssistantSession(data && data.status) ? responseSessionId : "";
      } else {
        mapped.assistantMutationSessionId = "";
        mapped.assistantConversationSessionId = shouldContinueAssistantSession(data && data.status) ? responseSessionId : "";
      }
      this.setData(mapped);
    } catch (err) {
      if (this._ignoredRequestTokens.has(requestToken)) {
        return;
      }
      const detail = err && err.responseData && err.responseData.detail;
      if (detail === "TEAM_READ_ONLY") {
        this.showReadonlyTip();
        return;
      }
      wx.showToast({ title: this.t("common.sendFailed"), icon: "none" });
    } finally {
      this.stopProcessingIndicator();
      this.stopGraphStatePolling();
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
      mapped.assistantGraphState = this.ensureVisibleGraphState(mapped.assistantGraphState, (data && data.session_id) || "");
      mapped.processingDots = 0;
      mapped.assistantGraphNodes = buildAssistantGraphNodes(mapped.assistantGraphState, this.data.graphI18n || {});
      mapped.assistantMutationSessionId = "";
      mapped.assistantConversationSessionId = "";
      this.setData(mapped);
    } catch (err) {
      const detail = err && err.responseData && err.responseData.detail;
      if (detail === "TEAM_READ_ONLY") {
        this.showReadonlyTip();
        return;
      }
      wx.showToast({ title: this.t("common.sendFailed"), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
