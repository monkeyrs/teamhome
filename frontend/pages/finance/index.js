const { request } = require("../../utils/request");
const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");

const DELETE_BUTTON_WIDTH = 88;
const HARD_DELETE_THRESHOLD = 160;
const MAX_SWIPE = 220;

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    records: [],
    hasTeam: true,
    teamReady: false,
    currentTeamId: "",
    form: {
      amount: "",
      type: "expense",
      category: "",
      placeName: "",
      placeLatitude: null,
      placeLongitude: null,
      note: ""
    },
    swipeStartX: 0
  },

  async onShow() {
    const { teamId } = getCurrentTeamState();
    if (!this.data.teamReady || this.data.currentTeamId !== teamId) {
      await this.initPage();
    }
  },

  async initPage() {
    this.setData({ loading: true });
    try {
      const { teamId, teams } = await bootstrapSession();
      this.setData({ teams, hasTeam: !!teamId, teamReady: true, currentTeamId: teamId });
      if (!teamId) {
        this.setData({ records: [] });
        return;
      }
      const teamIndex = Math.max(0, teams.findIndex((item) => item.id === teamId));
      this.setData({ teamIndex });
      await this.loadFinance(teamId);
    } catch (err) {
      wx.showToast({ title: "初始化失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  currentTeam() {
    return this.data.teams[this.data.teamIndex] || null;
  },

  async loadFinance(teamId) {
    const data = await request({ path: `/finance?team_id=${teamId}` });
    this.setData({
      records: (data || []).map((item) => ({
        ...item,
        creatorName: item.creator_nickname || "团队成员",
        offsetX: 0,
        deleteWidth: 0,
        amountText: `${item.type === "income" ? "+" : "-"}${item.amount}`,
        locationText: item.location || "未设置地点",
        createdText: item.created_at || ""
      }))
    });
  },

  goAssistantPage() {
    wx.switchTab({ url: "/pages/assistant/index" });
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

  chooseLocation() {
    wx.chooseLocation({
      success: (res) => {
        this.setData({
          "form.placeName": res.name || res.address || "",
          "form.placeLatitude": typeof res.latitude === "number" ? res.latitude : null,
          "form.placeLongitude": typeof res.longitude === "number" ? res.longitude : null
        });
      },
      fail: (err) => {
        if (err && /cancel/i.test(err.errMsg || "")) return;
        wx.showToast({ title: "地图选点失败", icon: "none" });
      }
    });
  },

  clearLocation() {
    this.setData({
      "form.placeName": "",
      "form.placeLatitude": null,
      "form.placeLongitude": null
    });
  },

  onTypeChange(event) {
    const index = Number(event.detail.value || 0);
    this.setData({ "form.type": index === 1 ? "income" : "expense" });
  },

  async createRecord() {
    const team = this.currentTeam();
    const form = this.data.form;
    if (!team || !form.amount || !form.category) {
      wx.showToast({ title: "请填写必填项", icon: "none" });
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
          location: form.placeName || null,
          location_latitude: form.placeLatitude,
          location_longitude: form.placeLongitude,
          note: form.note || null
        }
      });
      wx.showToast({ title: "创建成功", icon: "success" });
      this.setData({
        form: {
          amount: "",
          type: "expense",
          category: "",
          placeName: "",
          placeLatitude: null,
          placeLongitude: null,
          note: ""
        }
      });
      await this.loadFinance(team.id);
    } catch (err) {
      wx.showToast({ title: "创建失败", icon: "none" });
    }
  },

  onSwipeStart(event) {
    this.setData({ swipeStartX: event.changedTouches[0].clientX });
  },

  onSwipeMove(event) {
    const currentX = event.changedTouches[0].clientX;
    const deltaX = currentX - this.data.swipeStartX;
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const records = this.data.records.slice();
    records.forEach((item, itemIndex) => {
      if (itemIndex !== index) {
        item.offsetX = 0;
        item.deleteWidth = 0;
      }
    });
    const offsetX = deltaX < 0 ? Math.max(deltaX, -MAX_SWIPE) : 0;
    records[index].offsetX = offsetX;
    records[index].deleteWidth = Math.min(Math.abs(offsetX), MAX_SWIPE);
    this.setData({ records });
  },

  async onSwipeEnd(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const records = this.data.records.slice();
    const current = records[index];
    if (!current) return;
    if (Math.abs(current.offsetX) >= HARD_DELETE_THRESHOLD) {
      await this.deleteRecordByIndex(index);
      return;
    }
    const shouldOpen = Math.abs(current.offsetX) >= DELETE_BUTTON_WIDTH / 2;
    current.offsetX = shouldOpen ? -DELETE_BUTTON_WIDTH : 0;
    current.deleteWidth = shouldOpen ? DELETE_BUTTON_WIDTH : 0;
    this.setData({ records });
  },

  async onTapDelete(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    await this.deleteRecordByIndex(index);
  },

  async deleteRecordByIndex(index) {
    const current = this.data.records[index];
    const team = this.currentTeam();
    if (!current || !team) return;
    try {
      await request({ path: `/finance/${current.id}`, method: "DELETE" });
      wx.showToast({ title: "已删除，可在最近修改中恢复", icon: "none" });
      await this.loadFinance(team.id);
    } catch (err) {
      wx.showToast({ title: "删除失败", icon: "none" });
    }
  }
});
