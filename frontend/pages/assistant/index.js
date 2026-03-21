const { request, uploadFile, setCurrentTeamId } = require("../../utils/request");
const { bootstrapSession } = require("../../utils/bootstrap");

const recorderManager = wx.getRecorderManager();

Page({
  data: {
    teams: [],
    teamIndex: 0,
    teamName: "",
    teamPanelOpen: false,
    profileDialogOpen: false,
    nicknameDraft: "",
    question: "",
    loading: false,
    recording: false,
    answer: "",
    answerDataText: ""
  },

  onLoad() {
    recorderManager.onStop(async (result) => {
      this.setData({ recording: false });
      if (!result.tempFilePath) return;
      try {
        const data = await uploadFile({
          path: "/assistant/transcribe",
          filePath: result.tempFilePath
        });
        const text = (data.text || "").trim();
        if (!text) {
          wx.showToast({ title: "未识别到语音", icon: "none" });
          return;
        }
        this.setData({ question: text });
        await this.askAssistant();
      } catch (err) {
        const message = (err.responseData && err.responseData.detail) || "语音转写失败";
        wx.showToast({ title: message, icon: "none" });
      }
    });
  },

  async onShow() {
    await this.initPage();
  },

  async initPage() {
    this.setData({ loading: true });
    try {
      const { teamId, teams } = await bootstrapSession();
      const user = getApp().globalData.user || {};
      const teamIndex = Math.max(0, teams.findIndex((item) => item.id === teamId));
      this.setData({
        teams,
        teamIndex: teamIndex < 0 ? 0 : teamIndex,
        teamPanelOpen: teams.length === 0,
        profileDialogOpen: !user.nickname || user.nickname === "微信用户",
        nicknameDraft: user.nickname && user.nickname !== "微信用户" ? user.nickname : ""
      });
    } catch (err) {
      wx.showToast({ title: "初始化失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  currentTeam() {
    return this.data.teams[this.data.teamIndex] || null;
  },

  toggleTeamPanel() {
    this.setData({ teamPanelOpen: !this.data.teamPanelOpen });
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

  onNicknameInput(event) {
    this.setData({ nicknameDraft: event.detail.value });
  },

  async saveNickname() {
    const nickname = (this.data.nicknameDraft || "").trim();
    if (!nickname) {
      wx.showToast({ title: "请输入昵称", icon: "none" });
      return;
    }
    try {
      const user = await request({
        path: "/auth/me",
        method: "PUT",
        data: { nickname }
      });
      getApp().globalData.user = user;
      wx.setStorageSync("user", user);
      this.setData({ profileDialogOpen: false, nicknameDraft: user.nickname || "" });
      wx.showToast({ title: "昵称已保存", icon: "success" });
    } catch (err) {
      wx.showToast({ title: "保存昵称失败", icon: "none" });
    }
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
      wx.showToast({ title: "请输入团队名", icon: "none" });
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
      wx.showToast({ title: "已加入团队", icon: "success" });
    } catch (err) {
      wx.showToast({
        title: "团队名仅支持中文、英文、数字，且不超过20个字符",
        icon: "none"
      });
    }
  },

  confirmLeaveTeam(event) {
    const teamId = event.currentTarget.dataset.teamId;
    const teamName = event.currentTarget.dataset.teamName;
    wx.showModal({
      title: "退出团队",
      content: `是否退出团队「${teamName}」？`,
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await request({
            path: `/teams/${teamId}/members/me`,
            method: "DELETE"
          });
          await this.refreshTeams();
          this.setData({ teamPanelOpen: this.data.teams.length === 0 });
          wx.showToast({ title: "已退出团队", icon: "success" });
        } catch (err) {
          wx.showToast({ title: "退出失败", icon: "none" });
        }
      }
    });
  },

  async undoLastDelete() {
    const team = this.currentTeam();
    if (!team) {
      wx.showToast({ title: "请先创建或加入团队", icon: "none" });
      return;
    }
    const confirmed = await new Promise((resolve) => {
      wx.showModal({
        title: "确认撤销",
        content: "将恢复最近一次删除的记录，是否继续？",
        success: (res) => resolve(!!res.confirm),
        fail: () => resolve(false)
      });
    });
    if (!confirmed) {
      return;
    }
    try {
      await request({
        path: `/changes/undo?team_id=${team.id}`,
        method: "POST"
      });
      wx.showToast({ title: "已恢复最近删除", icon: "success" });
    } catch (err) {
      wx.showToast({ title: "没有可恢复的删除", icon: "none" });
    }
  },

  startRecording() {
    if (this.data.recording) return;
    this.setData({ recording: true });
    recorderManager.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 96000,
      format: "mp3"
    });
  },

  stopRecording() {
    if (!this.data.recording) return;
    recorderManager.stop();
  },

  async askAssistant() {
    const team = this.currentTeam();
    const question = (this.data.question || "").trim();
    if (!team) {
      wx.showToast({ title: "请先创建或加入团队", icon: "none" });
      return;
    }
    if (!question) {
      wx.showToast({ title: "请输入问题", icon: "none" });
      return;
    }
    this.setData({ loading: true });
    try {
      const data = await request({
        path: "/finance/assistant",
        method: "POST",
        data: {
          team_id: team.id,
          question
        }
      });
      this.setData({
        answer: data.answer || "暂无回答",
        answerDataText: data.data ? JSON.stringify(data.data) : ""
      });
    } catch (err) {
      wx.showToast({ title: "发送失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
