const { request } = require("../../utils/request");
const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");

const DELETE_BUTTON_WIDTH = 88;
const EDIT_BUTTON_WIDTH = 88;
const HARD_ACTION_THRESHOLD = 160;
const MAX_SWIPE = 220;
const SWIPE_LAZINESS = 54;
const DIRECTION_LOCK_THRESHOLD = 12;

function buildEmptyForm() {
  return {
    amount: "",
    type: "expense",
    category: "",
    placeName: "",
    placeLatitude: null,
    placeLongitude: null,
    note: ""
  };
}

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    records: [],
    hasTeam: true,
    teamReady: false,
    currentTeamId: "",
    composerOpen: false,
    composerMode: "create",
    editingId: "",
    form: buildEmptyForm(),
    swipeStartX: 0,
    swipeStartY: 0,
    swipeDirection: ""
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
      this.setData({
        teams,
        hasTeam: !!teamId,
        teamReady: true,
        currentTeamId: teamId,
        composerOpen: false,
        composerMode: "create",
        editingId: "",
        form: buildEmptyForm()
      });
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
    const records = (data || [])
      .map((item) => ({
        ...item,
        creatorName: item.creator_nickname || "团队成员",
        amountText: `${item.type === "income" ? "+" : "-"}${item.amount}`,
        locationText: item.location || "未设置地点",
        createdText: item.created_at || "",
        recordSortTime: new Date(item.created_at || 0).getTime() || 0,
        offsetX: 0,
        deleteWidth: 0,
        editWidth: 0
      }))
      .sort((a, b) => b.recordSortTime - a.recordSortTime);
    this.setData({
      records
    });
  },

  openCreateComposer() {
    this.setData({
      composerOpen: true,
      composerMode: "create",
      editingId: "",
      form: buildEmptyForm()
    });
  },

  closeComposer() {
    this.setData({
      composerOpen: false,
      composerMode: "create",
      editingId: "",
      form: buildEmptyForm()
    });
  },

  openEditComposer(item) {
    if (!item) return;
    this.setData({
      composerOpen: true,
      composerMode: "edit",
      editingId: item.id,
      form: {
        amount: item.amount ? `${item.amount}` : "",
        type: item.type || "expense",
        category: item.category || "",
        placeName: item.location || "",
        placeLatitude: item.location_latitude,
        placeLongitude: item.location_longitude,
        note: item.note || ""
      }
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
    const type = event.currentTarget.dataset.type;
    if (!type) return;
    this.setData({ "form.type": type });
  },

  async submitRecord() {
    const team = this.currentTeam();
    const form = this.data.form;
    if (!team || !form.amount || !form.category) {
      wx.showToast({ title: "请填写必填项", icon: "none" });
      return;
    }

    const payload = {
      amount: Number(form.amount),
      type: form.type,
      category: form.category,
      location: form.placeName || null,
      location_latitude: form.placeLatitude,
      location_longitude: form.placeLongitude,
      note: form.note || null
    };

    try {
      if (this.data.composerMode === "edit" && this.data.editingId) {
        await request({
          path: `/finance/${this.data.editingId}`,
          method: "PUT",
          data: payload
        });
        wx.showToast({ title: "修改成功", icon: "success" });
      } else {
        await request({
          path: "/finance",
          method: "POST",
          data: {
            ...payload,
            team_id: team.id
          }
        });
        wx.showToast({ title: "创建成功", icon: "success" });
      }
      this.closeComposer();
      await this.loadFinance(team.id);
    } catch (err) {
      wx.showToast({ title: this.data.composerMode === "edit" ? "修改失败" : "创建失败", icon: "none" });
    }
  },

  closeSwipeRows(listKey) {
    const items = this.data[listKey].slice();
    items.forEach((item) => {
      item.offsetX = 0;
      item.deleteWidth = 0;
      item.editWidth = 0;
    });
    this.setData({ [listKey]: items });
  },

  onSwipeStart(event) {
    this.setData({
      swipeStartX: event.changedTouches[0].clientX,
      swipeStartY: event.changedTouches[0].clientY,
      swipeDirection: ""
    });
  },

  onSwipeMove(event) {
    const currentX = event.changedTouches[0].clientX;
    const currentY = event.changedTouches[0].clientY;
    const deltaX = currentX - this.data.swipeStartX;
    const deltaY = currentY - this.data.swipeStartY;
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;

    let direction = this.data.swipeDirection;
    if (!direction) {
      if (Math.abs(deltaX) < DIRECTION_LOCK_THRESHOLD && Math.abs(deltaY) < DIRECTION_LOCK_THRESHOLD) {
        return;
      }
      direction = Math.abs(deltaY) >= Math.abs(deltaX) ? "vertical" : "horizontal";
      this.setData({ swipeDirection: direction });
    }
    if (direction !== "horizontal") {
      return;
    }

    const records = this.data.records.slice();
    records.forEach((item, itemIndex) => {
      if (itemIndex !== index) {
        item.offsetX = 0;
        item.deleteWidth = 0;
        item.editWidth = 0;
      }
    });

    const horizontalDistance = Math.abs(deltaX);
    if (horizontalDistance <= SWIPE_LAZINESS) {
      records[index].offsetX = 0;
      records[index].deleteWidth = 0;
      records[index].editWidth = 0;
      this.setData({ records });
      return;
    }

    if (deltaX < 0) {
      const offsetX = Math.max(deltaX + SWIPE_LAZINESS, -MAX_SWIPE);
      records[index].offsetX = offsetX;
      records[index].deleteWidth = Math.min(Math.abs(offsetX), MAX_SWIPE);
      records[index].editWidth = 0;
    } else {
      const offsetX = Math.min(deltaX - SWIPE_LAZINESS, MAX_SWIPE);
      records[index].offsetX = offsetX;
      records[index].editWidth = Math.min(offsetX, MAX_SWIPE);
      records[index].deleteWidth = 0;
    }
    this.setData({ records });
  },

  async onSwipeEnd(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const records = this.data.records.slice();
    const current = records[index];
    if (!current) return;

    if (this.data.swipeDirection !== "horizontal") {
      current.offsetX = 0;
      current.deleteWidth = 0;
      current.editWidth = 0;
      this.setData({ records, swipeDirection: "" });
      return;
    }

    if (current.offsetX <= -HARD_ACTION_THRESHOLD) {
      await this.deleteRecordByIndex(index);
      this.setData({ swipeDirection: "" });
      return;
    }

    if (current.offsetX >= HARD_ACTION_THRESHOLD) {
      this.openEditComposer(current);
      this.closeSwipeRows("records");
      this.setData({ swipeDirection: "" });
      return;
    }

    if (current.offsetX < 0) {
      const shouldOpenDelete = Math.abs(current.offsetX) >= DELETE_BUTTON_WIDTH / 2;
      current.offsetX = shouldOpenDelete ? -DELETE_BUTTON_WIDTH : 0;
      current.deleteWidth = shouldOpenDelete ? DELETE_BUTTON_WIDTH : 0;
      current.editWidth = 0;
    } else {
      const shouldOpenEdit = current.offsetX >= EDIT_BUTTON_WIDTH / 2;
      current.offsetX = shouldOpenEdit ? EDIT_BUTTON_WIDTH : 0;
      current.editWidth = shouldOpenEdit ? EDIT_BUTTON_WIDTH : 0;
      current.deleteWidth = 0;
    }

    this.setData({ records, swipeDirection: "" });
  },

  async onTapDelete(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    await this.deleteRecordByIndex(index);
  },

  onTapEdit(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const current = this.data.records[index];
    this.openEditComposer(current);
    this.closeSwipeRows("records");
  },

  async deleteRecordByIndex(index) {
    const current = this.data.records[index];
    const team = this.currentTeam();
    if (!current || !team) return;
    try {
      await request({ path: `/finance/${current.id}`, method: "DELETE" });
      wx.showToast({ title: "已删除，可在助手中撤销", icon: "none" });
      await this.loadFinance(team.id);
    } catch (err) {
      wx.showToast({ title: "删除失败", icon: "none" });
    }
  }
});
