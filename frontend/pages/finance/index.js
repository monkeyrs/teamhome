const { request, setCurrentTeamId } = require("../../utils/request");
const { bootstrapSession } = require("../../utils/bootstrap");

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    records: [],
    form: {
      amount: "",
      type: "expense",
      category: "",
      note: ""
    },
    nlText: ""
  },

  async onShow() {
    await this.initPage();
  },

  async initPage() {
    this.setData({ loading: true });
    try {
      const { teamId, teams } = await bootstrapSession();
      const teamIndex = Math.max(
        0,
        teams.findIndex((item) => item.id === teamId)
      );
      this.setData({ teams, teamIndex });
      await this.loadFinance(teamId);
    } catch (err) {
      wx.showToast({ title: "Init failed", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  async loadFinance(teamId) {
    const data = await request({ path: `/finance?team_id=${teamId}` });
    this.setData({ records: data || [] });
  },

  onTeamChange(event) {
    const index = Number(event.detail.value || 0);
    const selected = this.data.teams[index];
    if (!selected) return;
    this.setData({ teamIndex: index });
    setCurrentTeamId(selected.id);
    this.loadFinance(selected.id).catch(() => {
      wx.showToast({ title: "Load failed", icon: "none" });
    });
  },

  onInputNL(event) {
    this.setData({ nlText: event.detail.value });
  },

  onInputAmount(event) {
    this.setData({ "form.amount": event.detail.value });
  },

  onInputCategory(event) {
    this.setData({ "form.category": event.detail.value });
  },

  onInputNote(event) {
    this.setData({ "form.note": event.detail.value });
  },

  onTypeChange(event) {
    const index = Number(event.detail.value || 0);
    this.setData({ "form.type": index === 1 ? "income" : "expense" });
  },

  async parseNL() {
    if (!this.data.nlText.trim()) return;
    try {
      const parsed = await request({
        path: "/finance/parse",
        method: "POST",
        data: { text: this.data.nlText.trim() }
      });
      this.setData({
        "form.amount": parsed.amount !== null && parsed.amount !== undefined ? String(parsed.amount) : this.data.form.amount,
        "form.type": parsed.type || this.data.form.type,
        "form.category": parsed.category || this.data.form.category
      });
      wx.showToast({ title: "Parsed", icon: "success" });
    } catch (err) {
      wx.showToast({ title: "Parse failed", icon: "none" });
    }
  },

  async createRecord() {
    const team = this.data.teams[this.data.teamIndex];
    const form = this.data.form;
    if (!team || !form.amount || !form.category) {
      wx.showToast({ title: "Missing required fields", icon: "none" });
      return;
    }
    try {
      await request({
        path: "/finance",
        method: "POST",
        data: {
          team_id: team.id,
          amount: Number(form.amount),
          type: form.type,
          category: form.category,
          note: form.note || null
        }
      });
      wx.showToast({ title: "Created", icon: "success" });
      this.setData({
        form: {
          amount: "",
          type: "expense",
          category: "",
          note: ""
        },
        nlText: ""
      });
      await this.loadFinance(team.id);
    } catch (err) {
      wx.showToast({ title: "Create failed", icon: "none" });
    }
  }
});
