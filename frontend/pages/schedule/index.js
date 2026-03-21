const { request } = require("../../utils/request");
const { bootstrapSession, getCurrentTeamState } = require("../../utils/bootstrap");

const DELETE_BUTTON_WIDTH = 88;
const EDIT_BUTTON_WIDTH = 88;
const HARD_ACTION_THRESHOLD = 160;
const MAX_SWIPE = 220;
const SWIPE_LAZINESS = 54;
const DIRECTION_LOCK_THRESHOLD = 12;

function pad(value) {
  return `${value}`.padStart(2, "0");
}

function formatDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function toLocalIso(datePart, timePart, allDay) {
  const finalTime = allDay ? "00:00" : (timePart || "00:00");
  return `${datePart}T${finalTime}:00+08:00`;
}

function buildEmptyForm(dateText) {
  return {
    title: "",
    description: "",
    placeName: "",
    placeLatitude: null,
    placeLongitude: null,
    is_all_day: false,
    date: dateText,
    start_clock: "09:00",
    end_date: dateText,
    end_clock: "10:00"
  };
}

Page({
  data: {
    loading: false,
    teams: [],
    teamIndex: 0,
    schedules: [],
    hasTeam: true,
    teamReady: false,
    currentTeamId: "",
    composerOpen: false,
    composerMode: "create",
    editingId: "",
    form: buildEmptyForm(formatDate(new Date())),
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
      const today = formatDate(new Date());
      this.setData({
        teams,
        hasTeam: !!teamId,
        teamReady: true,
        currentTeamId: teamId,
        composerOpen: false,
        composerMode: "create",
        editingId: "",
        form: buildEmptyForm(today)
      });
      if (!teamId) {
        this.setData({ schedules: [] });
        return;
      }
      const teamIndex = Math.max(0, teams.findIndex((item) => item.id === teamId));
      this.setData({ teamIndex });
      await this.loadSchedules(teamId);
    } catch (err) {
      wx.showToast({ title: "初始化失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  currentTeam() {
    return this.data.teams[this.data.teamIndex] || null;
  },

  async loadSchedules(teamId) {
    const data = await request({ path: `/schedules?team_id=${teamId}` });
    const schedules = (data || [])
      .map((item) => this.normalizeSchedule(item))
      .sort((a, b) => b.recordSortTime - a.recordSortTime);
    this.setData({
      schedules
    });
  },

  normalizeSchedule(item) {
    const creatorName = item.creator_nickname || "团队成员";
    return {
      ...item,
      creatorName,
      startText: this.formatDisplayTime(item.start_time, item.is_all_day),
      endText: item.end_time ? this.formatDisplayTime(item.end_time, item.is_all_day) : "未设置",
      statusText: item.status === "completed" ? "已完成" : item.status === "cancelled" ? "已取消" : "待处理",
      locationText: item.location || "未设置地点",
      recordSortTime: new Date(item.start_time || item.created_at || 0).getTime() || 0,
      offsetX: 0,
      deleteWidth: 0,
      editWidth: 0
    };
  },

  formatDisplayTime(value, isAllDay) {
    if (!value) return "未设置";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const dateText = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    return isAllDay ? `${dateText} 全天` : `${dateText} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  },

  resetForm() {
    const dateText = this.data.form.date || formatDate(new Date());
    this.setData({
      form: buildEmptyForm(dateText)
    });
  },

  openCreateComposer() {
    const dateText = this.data.form.date || formatDate(new Date());
    this.setData({
      composerOpen: true,
      composerMode: "create",
      editingId: "",
      form: buildEmptyForm(dateText)
    });
  },

  closeComposer() {
    const dateText = this.data.form.date || formatDate(new Date());
    this.setData({
      composerOpen: false,
      composerMode: "create",
      editingId: "",
      form: buildEmptyForm(dateText)
    });
  },

  openEditComposer(item) {
    if (!item) return;
    const start = item.start_time ? new Date(item.start_time) : new Date();
    const end = item.end_time ? new Date(item.end_time) : start;
    this.setData({
      composerOpen: true,
      composerMode: "edit",
      editingId: item.id,
      form: {
        title: item.title || "",
        description: item.description || "",
        placeName: item.location || "",
        placeLatitude: item.location_latitude,
        placeLongitude: item.location_longitude,
        is_all_day: !!item.is_all_day,
        date: formatDate(start),
        start_clock: `${pad(start.getHours())}:${pad(start.getMinutes())}`,
        end_date: formatDate(end),
        end_clock: `${pad(end.getHours())}:${pad(end.getMinutes())}`
      }
    });
  },

  goAssistantPage() {
    wx.switchTab({ url: "/pages/assistant/index" });
  },

  onInputTitle(event) {
    this.setData({ "form.title": event.detail.value });
  },

  onInputDescription(event) {
    this.setData({ "form.description": event.detail.value });
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

  onDateChange(event) {
    const date = event.detail.value;
    this.setData({
      "form.date": date,
      "form.end_date": this.data.form.end_date || date
    });
  },

  onTimeChange(event) {
    this.setData({ "form.start_clock": event.detail.value });
  },

  onEndDateChange(event) {
    this.setData({ "form.end_date": event.detail.value });
  },

  onEndTimeChange(event) {
    this.setData({ "form.end_clock": event.detail.value });
  },

  onToggleAllDay(event) {
    this.setData({ "form.is_all_day": !!event.detail.value.length });
  },

  async submitSchedule() {
    const team = this.currentTeam();
    const form = this.data.form;
    if (!team || !form.title || !form.date) {
      wx.showToast({ title: "请填写必填项", icon: "none" });
      return;
    }

    const payload = {
      title: form.title,
      description: form.description || null,
      location: form.placeName || null,
      location_latitude: form.placeLatitude,
      location_longitude: form.placeLongitude,
      is_all_day: form.is_all_day,
      start_time: toLocalIso(form.date, form.start_clock, form.is_all_day),
      end_time: toLocalIso(form.end_date || form.date, form.end_clock, form.is_all_day)
    };

    try {
      if (this.data.composerMode === "edit" && this.data.editingId) {
        await request({
          path: `/schedules/${this.data.editingId}`,
          method: "PUT",
          data: payload
        });
        wx.showToast({ title: "修改成功", icon: "success" });
      } else {
        await request({
          path: "/schedules",
          method: "POST",
          data: {
            ...payload,
            team_id: team.id
          }
        });
        wx.showToast({ title: "创建成功", icon: "success" });
      }
      this.closeComposer();
      await this.loadSchedules(team.id);
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

    const schedules = this.data.schedules.slice();
    schedules.forEach((item, itemIndex) => {
      if (itemIndex !== index) {
        item.offsetX = 0;
        item.deleteWidth = 0;
        item.editWidth = 0;
      }
    });

    const horizontalDistance = Math.abs(deltaX);
    if (horizontalDistance <= SWIPE_LAZINESS) {
      schedules[index].offsetX = 0;
      schedules[index].deleteWidth = 0;
      schedules[index].editWidth = 0;
      this.setData({ schedules });
      return;
    }

    let effectiveDeltaX = 0;
    if (deltaX < 0) {
      effectiveDeltaX = Math.max(deltaX + SWIPE_LAZINESS, -MAX_SWIPE);
      schedules[index].offsetX = effectiveDeltaX;
      schedules[index].deleteWidth = Math.min(Math.abs(effectiveDeltaX), MAX_SWIPE);
      schedules[index].editWidth = 0;
    } else {
      effectiveDeltaX = Math.min(deltaX - SWIPE_LAZINESS, MAX_SWIPE);
      schedules[index].offsetX = effectiveDeltaX;
      schedules[index].editWidth = Math.min(effectiveDeltaX, MAX_SWIPE);
      schedules[index].deleteWidth = 0;
    }
    this.setData({ schedules });
  },

  async onSwipeEnd(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const schedules = this.data.schedules.slice();
    const current = schedules[index];
    if (!current) return;

    if (this.data.swipeDirection !== "horizontal") {
      current.offsetX = 0;
      current.deleteWidth = 0;
      current.editWidth = 0;
      this.setData({ schedules, swipeDirection: "" });
      return;
    }

    if (current.offsetX <= -HARD_ACTION_THRESHOLD) {
      await this.deleteScheduleByIndex(index);
      this.setData({ swipeDirection: "" });
      return;
    }

    if (current.offsetX >= HARD_ACTION_THRESHOLD) {
      this.openEditComposer(current);
      this.closeSwipeRows("schedules");
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

    this.setData({ schedules, swipeDirection: "" });
  },

  async onTapDelete(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    await this.deleteScheduleByIndex(index);
  },

  onTapEdit(event) {
    const index = Number(event.currentTarget.dataset.index);
    if (Number.isNaN(index)) return;
    const current = this.data.schedules[index];
    this.openEditComposer(current);
    this.closeSwipeRows("schedules");
  },

  async deleteScheduleByIndex(index) {
    const current = this.data.schedules[index];
    const team = this.currentTeam();
    if (!current || !team) return;
    try {
      await request({ path: `/schedules/${current.id}`, method: "DELETE" });
      wx.showToast({ title: "已删除，可在助手中撤销", icon: "none" });
      await this.loadSchedules(team.id);
    } catch (err) {
      wx.showToast({ title: "删除失败", icon: "none" });
    }
  }
});
