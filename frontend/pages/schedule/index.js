const { request, setCurrentTeamId } = require("../../utils/request");
const { bootstrapSession } = require("../../utils/bootstrap");

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    schedules: [],
    form: {
      title: "",
      description: "",
      start_time: "",
      end_time: ""
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
      await this.loadSchedules(teamId);
    } catch (err) {
      wx.showToast({ title: "Init failed", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  async loadSchedules(teamId) {
    const data = await request({ path: `/schedules?team_id=${teamId}` });
    this.setData({ schedules: data || [] });
  },

  onTeamChange(event) {
    const index = Number(event.detail.value || 0);
    const selected = this.data.teams[index];
    if (!selected) return;
    this.setData({ teamIndex: index });
    setCurrentTeamId(selected.id);
    this.loadSchedules(selected.id).catch(() => {
      wx.showToast({ title: "Load failed", icon: "none" });
    });
  },

  onInputTitle(event) {
    this.setData({ "form.title": event.detail.value });
  },

  onInputDescription(event) {
    this.setData({ "form.description": event.detail.value });
  },

  onInputStart(event) {
    this.setData({ "form.start_time": event.detail.value });
  },

  onInputEnd(event) {
    this.setData({ "form.end_time": event.detail.value });
  },

  onInputNL(event) {
    this.setData({ nlText: event.detail.value });
  },

  async parseNL() {
    if (!this.data.nlText.trim()) return;
    try {
      const parsed = await request({
        path: "/schedules/parse",
        method: "POST",
        data: { text: this.data.nlText.trim() }
      });
      this.setData({
        "form.title": parsed.title || this.data.form.title,
        "form.start_time": parsed.start_time || this.data.form.start_time,
        "form.end_time": parsed.end_time || this.data.form.end_time
      });
      wx.showToast({ title: "Parsed", icon: "success" });
    } catch (err) {
      wx.showToast({ title: "Parse failed", icon: "none" });
    }
  },

  async createSchedule() {
    const team = this.data.teams[this.data.teamIndex];
    const form = this.data.form;
    if (!team || !form.title || !form.start_time) {
      wx.showToast({ title: "Missing required fields", icon: "none" });
      return;
    }
    try {
      await request({
        path: "/schedules",
        method: "POST",
        data: {
          team_id: team.id,
          title: form.title,
          description: form.description || null,
          start_time: form.start_time,
          end_time: form.end_time || null
        }
      });
      wx.showToast({ title: "Created", icon: "success" });
      this.setData({
        form: {
          title: "",
          description: "",
          start_time: "",
          end_time: ""
        },
        nlText: ""
      });
      await this.loadSchedules(team.id);
    } catch (err) {
      wx.showToast({ title: "Create failed", icon: "none" });
    }
  }
});
