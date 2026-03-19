const { request, setCurrentTeamId } = require("../../utils/request");
const { bootstrapSession } = require("../../utils/bootstrap");

Page({
  data: {
    teams: [],
    teamIndex: 0,
    question: "",
    loading: false,
    answer: "",
    answerData: null,
    answerDataText: ""
  },

  async onShow() {
    this.setData({ loading: true });
    try {
      const { teamId, teams } = await bootstrapSession();
      const teamIndex = Math.max(
        0,
        teams.findIndex((item) => item.id === teamId)
      );
      this.setData({ teams, teamIndex });
    } catch (err) {
      wx.showToast({ title: "Init failed", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  onTeamChange(event) {
    const index = Number(event.detail.value || 0);
    const selected = this.data.teams[index];
    if (!selected) return;
    this.setData({ teamIndex: index });
    setCurrentTeamId(selected.id);
  },

  onQuestionInput(event) {
    this.setData({ question: event.detail.value });
  },

  async askAssistant() {
    const team = this.data.teams[this.data.teamIndex];
    if (!team || !this.data.question.trim()) {
      wx.showToast({ title: "Question required", icon: "none" });
      return;
    }
    this.setData({ loading: true });
    try {
      const data = await request({
        path: "/finance/assistant",
        method: "POST",
        data: {
          team_id: team.id,
          question: this.data.question.trim()
        }
      });
      this.setData({
        answer: data.answer || "No answer",
        answerData: data.data || null,
        answerDataText: data.data ? JSON.stringify(data.data) : ""
      });
    } catch (err) {
      wx.showToast({ title: "Ask failed", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
